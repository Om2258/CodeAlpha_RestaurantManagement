import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import InventoryItem, MenuItem, Order, Reservation, Table


class RestaurantTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff", password="test-pass", is_staff=True)
        self.table = Table.objects.create(number=1, seats=4)
        self.pasta = MenuItem.objects.create(name="Pasta", price="12.50")
        self.stock = InventoryItem.objects.create(menu_item=self.pasta, quantity=8)

    def test_menu_list(self):
        response = self.client.get("/api/menu/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Pasta", response.content.decode())

    def test_reservation_rejects_overlapping_table_booking(self):
        start = timezone.now() + timedelta(days=4)
        first = self.client.post("/api/reservations/", data=json.dumps({
            "customer_name": "Asha", "customer_phone": "5550100",
            "table": self.table.id, "party_size": 3,
            "reservation_time": start.isoformat(),
        }), content_type="application/json")
        second = self.client.post("/api/reservations/", data=json.dumps({
            "customer_name": "Mina", "customer_phone": "5550101",
            "table": self.table.id, "party_size": 2,
            "reservation_time": (start + timedelta(minutes=45)).isoformat(),
        }), content_type="application/json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)

    def test_order_deducts_inventory(self):
        self.client.force_login(self.staff)
        response = self.client.post("/api/orders/", data=json.dumps({
            "table": self.table.id,
            "items": [{"menu_item": self.pasta.id, "quantity": 3}],
        }), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 5)

    def test_order_rejects_insufficient_inventory(self):
        self.client.force_login(self.staff)
        response = self.client.post("/api/orders/", data=json.dumps({
            "table": self.table.id,
            "items": [{"menu_item": self.pasta.id, "quantity": 9}],
        }), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Order.objects.count(), 0)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 8)

    def test_cancelling_order_restocks_inventory(self):
        self.client.force_login(self.staff)
        response = self.client.post("/api/orders/", data=json.dumps({
            "table": self.table.id,
            "items": [{"menu_item": self.pasta.id, "quantity": 2}],
        }), content_type="application/json")
        order_id = response.json()["id"]
        response = self.client.post(
            f"/api/orders/{order_id}/status/",
            data=json.dumps({"status": Order.Status.CANCELLED}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 8)

    def test_inventory_adjustment_requires_staff(self):
        response = self.client.post(
            "/api/inventory/",
            data=json.dumps({"inventory_item": self.stock.id, "amount": 5}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
