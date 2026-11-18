from django.urls import path
from . import views

urlpatterns = [
    path('', views.api),
    path('api/menu/', views.menu),
    path('api/tables/', views.tables),
    path('api/reservations/', views.reservations),
    path('api/orders/', views.orders),
    path('api/orders/<int:order_id>/status/', views.update_order_status),
    path('api/inventory/', views.inventory),
]
