import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from payouts.models import Merchant, LedgerEntry, Payout
from django.db import transaction

print("Clearing old seed data...")
LedgerEntry.objects.all().delete()
Payout.objects.all().delete()
Merchant.objects.all().delete()

print("Creating merchants...")

with transaction.atomic():
    # Merchant 1 — Rahul's Agency
    rahul = Merchant.objects.create(
        name="Rahul's Digital Agency",
        email="rahul@digitalagency.in",
        bank_account_number="1234567890",
        bank_ifsc="HDFC0001234"
    )

    # Give Rahul credits (simulated customer payments)
    LedgerEntry.objects.create(
        merchant=rahul,
        entry_type='credit',
        amount_paise=500000,  # ₹5000
        description='Payment from US client - Web Design Project'
    )
    LedgerEntry.objects.create(
        merchant=rahul,
        entry_type='credit',
        amount_paise=300000,  # ₹3000
        description='Payment from UK client - SEO Campaign'
    )
    LedgerEntry.objects.create(
        merchant=rahul,
        entry_type='credit',
        amount_paise=200000,  # ₹2000
        description='Payment from UAE client - Social Media'
    )

    print(f"✓ Created {rahul.name} - Balance: ₹{rahul.available_balance/100}")

    # Merchant 2 — Priya's Freelance
    priya = Merchant.objects.create(
        name="Priya Freelance Studio",
        email="priya@freelance.in",
        bank_account_number="9876543210",
        bank_ifsc="ICIC0009876"
    )

    LedgerEntry.objects.create(
        merchant=priya,
        entry_type='credit',
        amount_paise=750000,  # ₹7500
        description='Payment from Singapore client - App Development'
    )
    LedgerEntry.objects.create(
        merchant=priya,
        entry_type='credit',
        amount_paise=250000,  # ₹2500
        description='Payment from Canada client - Logo Design'
    )
    LedgerEntry.objects.create(
        merchant=priya,
        entry_type='debit',
        amount_paise=200000,  # ₹2000 already withdrawn
        description='Payout to ICICI bank - previous withdrawal'
    )

    print(f"✓ Created {priya.name} - Balance: ₹{priya.available_balance/100}")

    # Merchant 3 — Arjun's Store
    arjun = Merchant.objects.create(
        name="Arjun Online Store",
        email="arjun@store.in",
        bank_account_number="1122334455",
        bank_ifsc="SBI00011223"
    )

    LedgerEntry.objects.create(
        merchant=arjun,
        entry_type='credit',
        amount_paise=1000000,  # ₹10000
        description='Payment from USA client - Bulk Order'
    )
    LedgerEntry.objects.create(
        merchant=arjun,
        entry_type='credit',
        amount_paise=500000,  # ₹5000
        description='Payment from Germany client - Monthly Subscription'
    )
    LedgerEntry.objects.create(
        merchant=arjun,
        entry_type='debit',
        amount_paise=300000,  # ₹3000 already withdrawn
        description='Payout to SBI bank - previous withdrawal'
    )

    print(f"✓ Created {arjun.name} - Balance: ₹{arjun.available_balance/100}")

print("\n✅ Seed data created successfully!")
print("\nMerchant Summary:")
print(f"  {rahul.name}: ₹{rahul.available_balance/100} available")
print(f"  {priya.name}: ₹{priya.available_balance/100} available")
print(f"  {arjun.name}: ₹{arjun.available_balance/100} available")
print("\nCopy these merchant IDs for testing:")
print(f"  Rahul's ID:  {rahul.id}")
print(f"  Priya's ID:  {priya.id}")
print(f"  Arjun's ID:  {arjun.id}")