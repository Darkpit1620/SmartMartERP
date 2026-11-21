from django.urls import path
from . import views

app_name = 'reporting_insights'
urlpatterns = [
    path('', views.home, name='home'),
    path('export/', views.export_csv, name='export_csv'),
]
