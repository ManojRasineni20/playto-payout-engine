# EXPLAINER.md

## 1. The Ledger

**Balance calculation query:**

```python
from django.db.models import Sum

credits = self.ledger_entries.filter(
    entry_type='credit'
).aggregate(total=Sum('amount_paise'))['total'] or 0

debits = self.ledger_entries.filter(
    entry_type='debit'
).aggregate(total=Sum('amount_paise'))['total'] or 0

available_balance = credits - debits
```

**Why this model:**

I modelled credits and debits as separate immutable ledger entries rather than a single mutable balance field. This is the double-entry bookkeeping approach used by real payment systems.

The key reason: a mutable balance field is dangerous. If two requests update it simultaneously, you get a race condition and the balance becomes wrong. With ledger entries, every transaction is permanently recorded and the balance is always derived from the sum — it cannot drift.

I use database-level SUM aggregation (`aggregate(total=Sum(...))`) instead of fetching all rows and summing in Python. This means the database does one efficient query instead of loading potentially thousands of rows into memory.

Amounts are always stored as `BigIntegerField` in paise. ₹1 = 100 paise. No floats, no decimals. Floating point arithmetic is non-deterministic — `0.1 + 0.2 != 0.3` in Python. For money this is unacceptable.

---

## 2. The Lock

**Exact code that prevents overdrawing:**

```python
with transaction.atomic():
    locked_merchant = Merchant.objects.select_for_update().get(
        id=merchant_id
    )
    available = locked_merchant.available_balance

    if available < int(amount_paise):
        return Response({'error': 'Insufficient balance'}, status=400)

    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(entry_type='debit', ...)
```

**What database primitive it relies on:**

`select_for_update()` translates to `SELECT ... FOR UPDATE` in PostgreSQL. This acquires a row-level exclusive lock on the merchant row for the duration of the transaction.

When two requests arrive simultaneously for the same merchant:
- Request A acquires the lock and checks balance (₹10,000)
- Request B tries to acquire the lock but blocks — it waits
- Request A sees sufficient balance, creates the payout, debits ₹6,000, commits
- The lock is released
- Request B now acquires the lock, checks balance (now ₹4,000), sees insufficient funds, returns 400

This is a database-level lock, not a Python-level lock. Python threading locks don't work across multiple processes or servers. PostgreSQL row locks do — even with multiple Django workers running.

---

## 3. The Idempotency

**How the system knows it has seen a key before:**

Every successful payout request saves an `IdempotencyKey` record with:
- `merchant` (foreign key — keys are scoped per merchant)
- `key` (the UUID from the header)
- `response_data` (the exact JSON response we returned)

On every incoming request, before doing any work:

```python
existing_key = IdempotencyKey.objects.filter(
    merchant=merchant,
    key=idempotency_key
).first()

if existing_key:
    return Response(existing_key.response_data, status=200)
```

**What happens if the first request is still in flight when the second arrives:**

The `IdempotencyKey` record is created inside the same `transaction.atomic()` block as the payout. The unique constraint `unique_together = ['merchant', 'key']` on the model means if two requests with the same key hit the database simultaneously, one will get an `IntegrityError` and be rejected cleanly.

The key is saved only after the payout is successfully created — so a second request that arrives while the first is still processing will either:
1. Find the key already saved and return the cached response, or
2. Get an IntegrityError on the unique constraint and fail safely

Keys are scoped per merchant — the same UUID key from two different merchants creates two separate records.

---

## 4. The State Machine

**Where illegal transitions are blocked:**

In `payouts/models.py`, the `Payout` model defines:

```python
VALID_TRANSITIONS = {
    'pending': ['processing'],
    'processing': ['completed', 'failed'],
    'completed': [],
    'failed': [],
}

def transition_to(self, new_status):
    allowed = self.VALID_TRANSITIONS.get(self.status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Illegal transition: {self.status} -> {new_status}"
        )
    self.status = new_status
    self.save()
```

`completed` maps to an empty list — so `completed → pending` raises `ValueError`.
`failed` maps to an empty list — so `failed → completed` raises `ValueError`.

The background worker in `tasks.py` also enforces this at the database level by checking `payout.status != 'pending'` before processing, and only transitioning through the allowed path.

When a payout fails, the fund return happens atomically with the state transition inside a single `transaction.atomic()` block — so it is impossible for a payout to be marked failed without the funds being returned, or for funds to be returned without the payout being marked failed.

---

## 5. The AI Audit

**Where AI wrote subtly wrong code and what I caught:**

When I asked AI to write the balance check and deduction, it initially gave me this:

```python
# WRONG CODE - what AI gave
merchant = Merchant.objects.get(id=merchant_id)
available = merchant.available_balance

if available < amount_paise:
    return Response({'error': 'Insufficient balance'}, status=400)

payout = Payout.objects.create(...)
```

**The problem:** This is a classic check-then-act race condition. Between the `get()` and the `create()`, another request can read the same balance, both see sufficient funds, and both create payouts — overdrawing the merchant.

There is no database lock here. Two Python threads running simultaneously both read ₹10,000, both check `10000 >= 6000` (true), both create a ₹6,000 payout. The merchant ends up with -₹2,000.

**What I replaced it with:**

```python
# CORRECT CODE - what I used
with transaction.atomic():
    locked_merchant = Merchant.objects.select_for_update().get(
        id=merchant_id
    )
    available = locked_merchant.available_balance

    if available < int(amount_paise):
        return Response({'error': 'Insufficient balance'}, status=400)

    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(entry_type='debit', ...)
```

The fix: wrap everything in `transaction.atomic()` and use `select_for_update()`. Now the `SELECT FOR UPDATE` acquires a PostgreSQL row lock before reading the balance. The second request cannot read the balance until the first transaction commits. This eliminates the race condition at the database level — which is the only level that matters in a distributed system.
