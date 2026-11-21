from django.urls import path
from . import views

app_name = 'supplier_accounts'
urlpatterns = [
    path('', views.home, name='home'),
    path('export.csv', views.export_csv, name='export'),
    path('invoices/new/', views.invoice_new, name='invoice_new'),
    path('invoices/<int:pk>/', views.invoice_detail, name='detail'),
    path('invoices/<int:pk>/pay/', views.payment_new, name='payment_new'),
]
