from django.contrib import admin
from .models import InventoryAdjustment, InventoryItem, MenuItem, Order, OrderItem, Reservation, Table

admin.site.register((MenuItem, InventoryItem, InventoryAdjustment, Table, Reservation, Order, OrderItem))

# Register your models here.
