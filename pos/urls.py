from django.urls import path
from . import views

app_name = 'pos'
urlpatterns = [
    path('', views.index, name='index'),
    path('mode/', views.set_mode, name='set_mode'),
    path('cart/add/', views.add_item, name='add_item'),
    path('cart/update/', views.update_item, name='update_item'),
    path('checkout/', views.checkout, name='checkout'),
    path('sales/', views.sales, name='sales'),
    path('receipt/<int:pk>/', views.receipt, name='receipt'),
    path('receipt/<int:pk>/verify/', views.verify_payment, name='verify_payment'),
]
