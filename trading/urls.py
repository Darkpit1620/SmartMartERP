from django.urls import path
from . import views

app_name = 'trading'
urlpatterns = [
    path('', views.home, name='home'),
    path('suppliers/new/', views.supplier_new, name='supplier_new'),
    path('customers/new/', views.customer_new, name='customer_new'),
    path('purchasing/new/', views.purchase_new, name='purchase_new'),
    path('purchasing/<int:pk>/', views.purchase_detail, name='purchase_detail'),
    path('purchasing/<int:pk>/add/', views.purchase_add_line, name='purchase_add_line'),
    path('purchasing/<int:pk>/line/<int:line_id>/remove/', views.purchase_remove_line, name='purchase_remove_line'),
    path('purchasing/<int:pk>/place/', views.purchase_place, name='purchase_place'),
    path('purchasing/<int:pk>/receive/', views.purchase_receive, name='purchase_receive'),
    path('wholesale/new/', views.wholesale_new, name='wholesale_new'),
    path('wholesale/<int:pk>/', views.wholesale_detail, name='wholesale_detail'),
    path('wholesale/<int:pk>/add/', views.wholesale_add_line, name='wholesale_add_line'),
    path('wholesale/<int:pk>/line/<int:line_id>/remove/', views.wholesale_remove_line, name='wholesale_remove_line'),
    path('wholesale/<int:pk>/prepare/', views.wholesale_prepare, name='wholesale_prepare'),
    path('wholesale/<int:pk>/fulfill/', views.wholesale_fulfill, name='wholesale_fulfill'),
]
