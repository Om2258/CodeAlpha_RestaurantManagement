import json
from datetime import timedelta
from functools import wraps

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    InventoryAdjustment,
    InventoryItem,
    MenuItem,
    Order,
    OrderItem,
    Reservation,
    Table,
)


def api_login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Login required."}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def read_json(request):
    try:
        return json.loads(request.body or "{}"), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "Request body must be valid JSON."}, status=400)


def api(request):
    return JsonResponse({
        "service": "CodeAlpha Restaurant Management",
        "endpoints": [
            "/api/menu/", "/api/tables/", "/api/reservations/",
            "/api/orders/", "/api/inventory/",
        ],
    })


@require_http_methods(["GET", "POST"])
def menu(request):
    if request.method == "GET":
        return JsonResponse(list(MenuItem.objects.filter(available=True).values(
            "id", "name", "description", "price"
        )), safe=False)
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"error": "Staff login required."}, status=403)
    data, error = read_json(request)
    if error:
        return error
    try:
        item = MenuItem.objects.create(
            name=data["name"], description=data.get("description", ""), price=data["price"]
        )
        return JsonResponse({"id": item.id, "name": item.name}, status=201)
    except (KeyError, TypeError, ValueError, IntegrityError) as exc:
        return JsonResponse({"error": f"Invalid menu item: {exc}"}, status=400)


def table_available(table, at):
    window_end = at + timedelta(hours=2)
    return not Reservation.objects.filter(
        table=table,
        status=Reservation.Status.CONFIRMED,
        reservation_time__lt=window_end,
        reservation_time__gt=at - timedelta(hours=2),
    ).exists()


@require_http_methods(["GET", "POST"])
def tables(request):
    if request.method == "GET":
        at_value = request.GET.get("at")
        try:
            at = timezone.datetime.fromisoformat(at_value) if at_value else timezone.now()
            if timezone.is_naive(at):
                at = timezone.make_aware(at)
        except ValueError:
            return JsonResponse({"error": "at must be an ISO-8601 datetime."}, status=400)
        result = [{
            "id": table.id,
            "number": table.number,
            "seats": table.seats,
            "available": table_available(table, at),
        } for table in Table.objects.all()]
        return JsonResponse(result, safe=False)
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"error": "Staff login required."}, status=403)
    data, error = read_json(request)
    if error:
        return error
    try:
        table = Table.objects.create(number=data["number"], seats=data["seats"])
        return JsonResponse({"id": table.id, "number": table.number}, status=201)
    except (KeyError, TypeError, ValueError, IntegrityError) as exc:
        return JsonResponse({"error": f"Invalid table: {exc}"}, status=400)


@require_http_methods(["GET", "POST"])
def reservations(request):
    if request.method == "GET":
        return JsonResponse(list(Reservation.objects.values(
            "id", "customer_name", "table_id", "party_size", "reservation_time", "status"
        )), safe=False)
    data, error = read_json(request)
    if error:
        return error
    try:
        start = timezone.datetime.fromisoformat(data["reservation_time"].replace("Z", "+00:00"))
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        if start <= timezone.now():
            return JsonResponse({"error": "Reservation time must be in the future."}, status=400)
        with transaction.atomic():
            table = Table.objects.select_for_update().get(pk=data["table"])
            party_size = int(data["party_size"])
            if party_size < 1 or party_size > table.seats:
                return JsonResponse({"error": "Party size must fit the table."}, status=400)
            if not table_available(table, start):
                return JsonResponse({"error": "Table is already reserved for that time."}, status=409)
            reservation = Reservation.objects.create(
                customer_name=data["customer_name"],
                customer_phone=data["customer_phone"],
                table=table,
                party_size=party_size,
                reservation_time=start,
            )
        return JsonResponse({"id": reservation.id, "status": reservation.status}, status=201)
    except (KeyError, TypeError, ValueError, Table.DoesNotExist) as exc:
        return JsonResponse({"error": f"Invalid reservation: {exc}"}, status=400)


@api_login_required
@require_http_methods(["GET", "POST"])
def orders(request):
    if request.method == "GET":
        orders_qs = Order.objects.select_related("table").prefetch_related("items")
        if not request.user.is_staff:
            orders_qs = orders_qs.filter(server=request.user)
        return JsonResponse([{
            "id": order.id,
            "table": order.table.number,
            "status": order.status,
            "created_at": order.created_at,
            "items": list(order.items.values("id", "name")),
        } for order in orders_qs], safe=False)
    data, error = read_json(request)
    if error:
        return error
    entries = data.get("items")
    if not isinstance(entries, list) or not entries:
        return JsonResponse({"error": "items must be a non-empty list."}, status=400)
    try:
        with transaction.atomic():
            table = Table.objects.select_for_update().get(pk=data["table"])
            requested = {}
            for entry in entries:
                item_id = int(entry["menu_item"])
                quantity = int(entry["quantity"])
                if quantity < 1:
                    return JsonResponse({"error": "Item quantities must be positive."}, status=400)
                requested[item_id] = requested.get(item_id, 0) + quantity
            menu_items = {
                item.id: item for item in MenuItem.objects.select_for_update().filter(
                    id__in=requested, available=True
                )
            }
            if len(menu_items) != len(requested):
                return JsonResponse({"error": "One or more menu items do not exist or are unavailable."}, status=400)
            stock = {
                item.menu_item_id: item
                for item in InventoryItem.objects.select_for_update().filter(menu_item_id__in=requested)
            }
            for item_id, quantity in requested.items():
                if item_id not in stock or stock[item_id].quantity < quantity:
                    return JsonResponse({"error": f"Insufficient inventory for {menu_items[item_id].name}."}, status=409)
            order = Order.objects.create(table=table, server=request.user)
            for item_id, quantity in requested.items():
                inventory = stock[item_id]
                inventory.quantity -= quantity
                inventory.save(update_fields=["quantity"])
                OrderItem.objects.create(order=order, menu_item=menu_items[item_id], quantity=quantity)
                InventoryAdjustment.objects.create(
                    item=inventory, amount=-quantity, reason=f"Order {order.id}"
                )
        return JsonResponse({"id": order.id, "status": order.status}, status=201)
    except (KeyError, TypeError, ValueError, Table.DoesNotExist) as exc:
        return JsonResponse({"error": f"Invalid order: {exc}"}, status=400)


@api_login_required
@require_http_methods(["POST"])
def update_order_status(request, order_id):
    data, error = read_json(request)
    if error:
        return error
    status = data.get("status")
    if status not in Order.Status.values:
        return JsonResponse({"error": "Unknown order status."}, status=400)
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            if not request.user.is_staff and order.server_id != request.user.id:
                return JsonResponse({"error": "You cannot update this order."}, status=403)
            if order.status == Order.Status.CANCELLED:
                return JsonResponse({"error": "Cancelled orders cannot be changed."}, status=409)
            if status == Order.Status.CANCELLED:
                for line in order.orderitem_set.select_related("menu_item__inventory"):
                    inventory = InventoryItem.objects.select_for_update().get(menu_item=line.menu_item)
                    inventory.quantity += line.quantity
                    inventory.save(update_fields=["quantity"])
                    InventoryAdjustment.objects.create(
                        item=inventory, amount=line.quantity, reason=f"Cancelled order {order.id}"
                    )
            order.status = status
            order.save(update_fields=["status"])
        return JsonResponse({"id": order.id, "status": order.status})
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found."}, status=404)
    except InventoryItem.DoesNotExist:
        return JsonResponse({"error": "Inventory record missing for order item."}, status=409)


@api_login_required
@require_http_methods(["GET", "POST"])
def inventory(request):
    if not request.user.is_staff:
        return JsonResponse({"error": "Staff login required."}, status=403)
    if request.method == "GET":
        return JsonResponse([{
            "id": stock.id,
            "menu_item": stock.menu_item.name,
            "quantity": stock.quantity,
            "low_stock": stock.quantity <= stock.low_stock_threshold,
        } for stock in InventoryItem.objects.select_related("menu_item")], safe=False)
    data, error = read_json(request)
    if error:
        return error
    try:
        amount = int(data["amount"])
        if amount == 0:
            return JsonResponse({"error": "amount cannot be zero."}, status=400)
        with transaction.atomic():
            stock = InventoryItem.objects.select_for_update().get(pk=data["inventory_item"])
            if stock.quantity + amount < 0:
                return JsonResponse({"error": "Inventory cannot be reduced below zero."}, status=409)
            stock.quantity += amount
            stock.save(update_fields=["quantity"])
            InventoryAdjustment.objects.create(
                item=stock, amount=amount, reason=data.get("reason", "Manual adjustment")
            )
        return JsonResponse({"id": stock.id, "quantity": stock.quantity})
    except (KeyError, TypeError, ValueError, InventoryItem.DoesNotExist) as exc:
        return JsonResponse({"error": f"Invalid inventory adjustment: {exc}"}, status=400)
