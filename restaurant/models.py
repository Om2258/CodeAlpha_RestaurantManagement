from django.contrib.auth.models import User
from django.db import models


class MenuItem(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    available = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    menu_item = models.OneToOneField(MenuItem, on_delete=models.CASCADE, related_name="inventory")
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)


class Table(models.Model):
    number = models.PositiveIntegerField(unique=True)
    seats = models.PositiveIntegerField()

    def __str__(self):
        return f"Table {self.number}"


class Reservation(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=30)
    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name="reservations")
    party_size = models.PositiveIntegerField()
    reservation_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)


class Order(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PREPARING = "preparing", "Preparing"
        SERVED = "served", "Served"
        CANCELLED = "cancelled", "Cancelled"

    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name="orders")
    server = models.ForeignKey(User, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    items = models.ManyToManyField(MenuItem, through="OrderItem")


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()


class InventoryAdjustment(models.Model):
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="adjustments")
    amount = models.IntegerField()
    reason = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)
