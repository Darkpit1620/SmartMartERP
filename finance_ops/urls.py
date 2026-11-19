from django.urls import path
from . import views

app_name = 'finance_ops'

urlpatterns = [
    path('', views.overview, name='overview'),
    path('expenses/', views.expenses, name='expenses'),
    path('expenses/new/', views.new_expense, name='new_expense'),
    path('expenses/<int:pk>/review/', views.review, name='review'),
    path('report.csv', views.export_report, name='export_report'),
]
