from celery import shared_task
from django.db import transaction
from django.utils import timezone
import random
import time


@shared_task(bind=True, max_retries=3)
def process_payout(self, payout_id):
    from .models import Payout, LedgerEntry

    try:
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(id=payout_id)

            # Only process pending payouts
            if payout.status != 'pending':
                return f'Payout {payout_id} is already {payout.status}'

            # Move to processing
            payout.status = 'processing'
            payout.attempts += 1
            payout.save()

        # Simulate bank API call (outside the lock)
        time.sleep(2)

        # Simulate: 70% success, 20% fail, 10% hang
        outcome = random.random()

        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(id=payout_id)

            if outcome < 0.70:
                # Success
                payout.status = 'completed'
                payout.processed_at = timezone.now()
                payout.save()
                return f'Payout {payout_id} completed successfully'

            elif outcome < 0.90:
                # Failure — return funds to merchant
                payout.status = 'failed'
                payout.processed_at = timezone.now()
                payout.save()

                # Refund the held amount back to merchant balance
                LedgerEntry.objects.create(
                    merchant=payout.merchant,
                    entry_type='credit',
                    amount_paise=payout.amount_paise,
                    description=f'Refund for failed payout {payout.id}'
                )
                return f'Payout {payout_id} failed, funds returned'

            else:
                # Hang — retry with exponential backoff
                raise self.retry(
                    countdown=30 * (2 ** self.request.retries),
                    exc=Exception('Bank API timeout')
                )

    except Payout.DoesNotExist:
        return f'Payout {payout_id} not found'
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # Max retries reached — mark as failed and return funds
            with transaction.atomic():
                try:
                    payout = Payout.objects.select_for_update().get(id=payout_id)
                    if payout.status == 'processing':
                        payout.status = 'failed'
                        payout.processed_at = timezone.now()
                        payout.save()
                        LedgerEntry.objects.create(
                            merchant=payout.merchant,
                            entry_type='credit',
                            amount_paise=payout.amount_paise,
                            description=f'Refund for timed out payout {payout.id}'
                        )
                except Payout.DoesNotExist:
                    pass
        raise exc