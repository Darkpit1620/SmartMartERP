from django.urls import path
from . import views

app_name = 'sales_documents'
urlpatterns = [
    path('', views.home, name='home'),
    path('brand/', views.brand_settings, name='brand_settings'),
    path('receipt/<int:pk>/', views.thermal_receipt, name='thermal_receipt'),
    path('invoice/<int:pk>/', views.commercial_invoice, name='commercial_invoice'),
    path('invoice/<int:pk>/customer/', views.customer_details, name='customer_details'),
]
