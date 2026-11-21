from django.urls import path
from . import views

app_name = 'returns_ops'
urlpatterns = [
    path('', views.home, name='home'),
    path('sale/<int:pk>/new/', views.new_return, name='new'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/review/', views.review, name='review'),
    path('<int:pk>/record-refund/', views.record_refund, name='record_refund'),
]
