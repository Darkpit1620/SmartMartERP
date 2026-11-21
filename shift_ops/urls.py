from django.urls import path
from . import views

app_name = 'shift_ops'
urlpatterns = [
    path('', views.home, name='home'),
    path('open/', views.start, name='start'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/cash-entry/', views.entry, name='entry'),
    path('<int:pk>/close/', views.finish, name='finish'),
    path('<int:pk>/review/', views.review, name='review'),
]
