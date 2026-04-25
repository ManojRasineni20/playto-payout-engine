from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Merchant, LedgerEntry, Payout, IdempotencyKey
from .serializers import PayoutSerializer
import uuid


class PayoutRequestView(APIView):

    def post(self, request):
        # Step 1: Get the idempotency key from header
        idempotency_key = request.headers.get('Idempotency-Key')
        if not idempotency_key:
            return Response(
                {'error': 'Idempotency-Key header is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 2: Get merchant (in real app this comes from auth)
        merchant_id = request.data.get('merchant_id')
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response(
                {'error': 'Merchant not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Step 3: Check if we have seen this idempotency key before
        existing_key = IdempotencyKey.objects.filter(
            merchant=merchant,
            key=idempotency_key
        ).first()

        if existing_key:
            # Return the exact same response as the first time
            return Response(
                existing_key.response_data,
                status=status.HTTP_200_OK
            )

        # Step 4: Validate request data
        amount_paise = request.data.get('amount_paise')
        bank_account_id = request.data.get('bank_account_id')

        if not amount_paise or not bank_account_id:
            return Response(
                {'error': 'amount_paise and bank_account_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if int(amount_paise) <= 0:
            return Response(
                {'error': 'amount_paise must be positive'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 5: The critical section — use database lock to prevent race conditions
        try:
            with transaction.atomic():
                # Lock this merchant's row so no other request can touch it
                # until we're done. This is SELECT FOR UPDATE.
                locked_merchant = Merchant.objects.select_for_update().get(
                    id=merchant_id
                )

                # Calculate available balance inside the lock
                available = locked_merchant.available_balance

                if available < int(amount_paise):
                    return Response(
                        {
                            'error': 'Insufficient balance',
                            'available_paise': available,
                            'requested_paise': int(amount_paise)
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Create the payout
                payout = Payout.objects.create(
                    merchant=locked_merchant,
                    amount_paise=int(amount_paise),
                    bank_account_id=bank_account_id,
                    status='pending'
                )

                # Create a debit ledger entry to hold the funds
                LedgerEntry.objects.create(
                    merchant=locked_merchant,
                    entry_type='debit',
                    amount_paise=int(amount_paise),
                    description=f'Hold for payout {payout.id}'
                )

                # Build the response
                response_data = {
                    'payout_id': str(payout.id),
                    'merchant_id': str(locked_merchant.id),
                    'amount_paise': payout.amount_paise,
                    'bank_account_id': payout.bank_account_id,
                    'status': payout.status,
                    'created_at': payout.created_at.isoformat(),
                }

                # Save the idempotency key so duplicate requests return same response
                IdempotencyKey.objects.create(
                    merchant=locked_merchant,
                    key=idempotency_key,
                    response_data=response_data
                )

                # Trigger background worker to process the payout
                from .tasks import process_payout
                process_payout.delay(str(payout.id))

                return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MerchantBalanceView(APIView):

    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response(
                {'error': 'Merchant not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        ledger_entries = merchant.ledger_entries.all()[:20]
        payouts = merchant.payouts.all()[:20]

        return Response({
            'merchant_id': str(merchant.id),
            'merchant_name': merchant.name,
            'available_balance_paise': merchant.available_balance,
            'held_balance_paise': merchant.held_balance,
            'ledger_entries': [
                {
                    'id': str(e.id),
                    'type': e.entry_type,
                    'amount_paise': e.amount_paise,
                    'description': e.description,
                    'created_at': e.created_at.isoformat(),
                }
                for e in ledger_entries
            ],
            'payouts': [
                {
                    'id': str(p.id),
                    'amount_paise': p.amount_paise,
                    'status': p.status,
                    'created_at': p.created_at.isoformat(),
                }
                for p in payouts
            ]
        })


class PayoutStatusView(APIView):

    def get(self, request, payout_id):
        try:
            payout = Payout.objects.get(id=payout_id)
        except Payout.DoesNotExist:
            return Response(
                {'error': 'Payout not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            'payout_id': str(payout.id),
            'merchant_id': str(payout.merchant.id),
            'amount_paise': payout.amount_paise,
            'status': payout.status,
            'attempts': payout.attempts,
            'created_at': payout.created_at.isoformat(),
            'updated_at': payout.updated_at.isoformat(),
        })