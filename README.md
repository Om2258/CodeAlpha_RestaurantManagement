# CodeAlpha Restaurant Management System

Django and SQLite REST API for CodeAlpha Backend Development Task 3.

## Features

- Menu, table, reservation, order, and inventory models
- Reservations check party size and prevent overlapping bookings for two-hour windows
- Staff-authenticated order creation validates stock and deducts inventory in a transaction
- Cancelling an order restores stock; inventory adjustments are audited
- Staff-only inventory updates and low-stock visibility
- Django admin dashboard

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Set `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=0` before deploying. Authenticated write endpoints use Django session authentication and CSRF protection.

## API

- `GET /api/menu/` — list available menu items
- `GET /api/tables/?at=2026-12-01T19:00:00Z` — table capacity and availability at a time
- `POST /api/reservations/` — reserve a table (`customer_name`, `customer_phone`, `table`, `party_size`, `reservation_time`)
- `GET|POST /api/orders/` — view orders or place an order (`table`, `items: [{menu_item, quantity}]`); requires staff login
- `POST /api/orders/<id>/status/` — set `open`, `preparing`, `served`, or `cancelled`; cancellation restores stock
- `GET|POST /api/inventory/` — staff view/adjust stock (`inventory_item`, nonzero `amount`, optional `reason`)

Manage menu, tables, and inventory records through Django admin. Run tests with `python manage.py test`.
