from django.urls import path
from . import views

app_name = 'transfers'
urlpatterns = [
    path('', views.transfer_list, name='list'),
    path('new/', views.transfer_new, name='new'),
    path('<int:pk>/', views.transfer_detail, name='detail'),
    path('<int:pk>/add/', views.transfer_add, name='add'),
    path('<int:pk>/remove/<int:line_id>/', views.transfer_remove, name='remove'),
    path('<int:pk>/dispatch/', views.transfer_dispatch, name='dispatch'),
    path('<int:pk>/receive/', views.transfer_receive, name='receive'),
]
