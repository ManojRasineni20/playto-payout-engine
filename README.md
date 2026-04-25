# Playto Payout Engine

A production-grade payout engine for Indian merchants to collect international payments and withdraw to their Indian bank accounts.

## Tech Stack

- **Backend:** Django 6.0 + Django REST Framework
- **Frontend:** React + Tailwind CSS
- **Database:** PostgreSQL (amounts stored as BigIntegerField in paise)
- **Background Jobs:** Celery + Redis
- **Testing:** Django TestCase + TransactionTestCase

## Architecture

## Core Features

- Merchant ledger with credits and debits in paise (never floats)
- Payout request API with idempotency key support
- Concurrent payout protection using SELECT FOR UPDATE
- State machine: pending → processing → completed/failed
- Background worker with exponential backoff retry (max 3 attempts)
- React dashboard with live balance and payout history

## Setup Instructions

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 15+
- Redis (or Memurai on Windows)

### Backend Setup

```bash
# Clone the repo
git clone https://github.com/ManojRasineni20/playto-payout-engine.git
cd playto-payout-engine

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install django djangorestframework psycopg2-binary celery redis django-celery-results django-cors-headers

# Create PostgreSQL database
psql -U postgres -c "CREATE DATABASE playto_db;"

# Update config/settings.py with your DB password

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Seed merchants
python seed.py

# Start Django server
python manage.py runserver
```

### Celery Worker Setup

```bash
# In a new terminal (with venv activated)
celery -A config worker --loglevel=info --pool=solo
```

### Frontend Setup

```bash
cd frontend
npm install
npm start
```

### Run Tests

```bash
python manage.py test payouts
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/payouts/ | Request a payout |
| GET | /api/v1/merchants/{id}/ | Get merchant balance + history |
| GET | /api/v1/payouts/{id}/ | Get payout status |

## Test Merchants (after seeding)

| Merchant | Balance |
|----------|---------|
| Rahul's Digital Agency | ₹10,000 |
| Priya Freelance Studio | ₹8,000 |
| Arjun Online Store | ₹12,000 |

## Running Tests

```bash
python manage.py test payouts -v 2
```

Two tests included:
- **ConcurrencyTest** - Verifies two simultaneous 60% balance requests result in exactly one success
- **IdempotencyTest** - Verifies same idempotency key returns identical response with no duplicate payout