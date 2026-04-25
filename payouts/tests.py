from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from concurrent.futures import ThreadPoolExecutor, as_completed
from .models import Merchant, LedgerEntry, Payout
import uuid


def create_test_merchant(name="Test Merchant", balance_paise=10000):
    merchant = Merchant.objects.create(
        name=name,
        email=f"{uuid.uuid4()}@test.com",
        bank_account_number="1234567890",
        bank_ifsc="HDFC0001234"
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        entry_type='credit',
        amount_paise=balance_paise,
        description='Test credit'
    )
    return merchant


class ConcurrencyTest(TransactionTestCase):
    """
    Uses TransactionTestCase so threads can actually see
    each other's database writes — required for SELECT FOR UPDATE to work.
    """

    def test_concurrent_payouts_no_overdraw(self):
        merchant = create_test_merchant(balance_paise=10000)
        merchant_id = str(merchant.id)

        statuses = []

        def make_request(idem_key):
            client = APIClient()
            response = client.post(
                '/api/v1/payouts/',
                {
                    'merchant_id': merchant_id,
                    'amount_paise': 6000,
                    'bank_account_id': 'ACC123'
                },
                format='json',
                HTTP_IDEMPOTENCY_KEY=idem_key
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(make_request, str(uuid.uuid4())),
                executor.submit(make_request, str(uuid.uuid4())),
            ]
            for f in as_completed(futures):
                statuses.append(f.result())

        print(f"\nConcurrency test statuses: {statuses}")

        successes = statuses.count(201)
        failures = statuses.count(400)

        print(f"Successes: {successes}, Failures: {failures}")

        self.assertEqual(successes, 1, "Exactly one payout should succeed")
        self.assertEqual(failures, 1, "Exactly one should be rejected")

        # Check total debited never exceeds balance
        from django.db.models import Sum
        total_debited = LedgerEntry.objects.filter(
            merchant_id=merchant_id,
            entry_type='debit'
        ).aggregate(total=Sum('amount_paise'))['total'] or 0

        self.assertLessEqual(total_debited, 10000)
        print(f"Balance integrity: {total_debited} paise debited from 10000 ✅")


class IdempotencyTest(TestCase):
    """
    Same idempotency key twice must return same response,
    with only one payout created in the database.
    """

    def test_duplicate_request_returns_same_response(self):
        merchant = create_test_merchant(balance_paise=50000)
        client = APIClient()
        idempotency_key = str(uuid.uuid4())

        response1 = client.post(
            '/api/v1/payouts/',
            {
                'merchant_id': str(merchant.id),
                'amount_paise': 5000,
                'bank_account_id': 'ACC123'
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key
        )

        response2 = client.post(
            '/api/v1/payouts/',
            {
                'merchant_id': str(merchant.id),
                'amount_paise': 5000,
                'bank_account_id': 'ACC123'
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key
        )

        print(f"\nFirst status: {response1.status_code}")
        print(f"Second status: {response2.status_code}")
        print(f"First payout ID:  {response1.data.get('payout_id')}")
        print(f"Second payout ID: {response2.data.get('payout_id')}")

        self.assertIn('payout_id', response1.data)
        self.assertIn('payout_id', response2.data)

        self.assertEqual(
            response1.data['payout_id'],
            response2.data['payout_id'],
            "Same key must return same payout ID"
        )

        payout_count = Payout.objects.filter(merchant=merchant).count()
        self.assertEqual(payout_count, 1, "Only one payout must exist")
        print(f"Only {payout_count} payout in DB ✅")