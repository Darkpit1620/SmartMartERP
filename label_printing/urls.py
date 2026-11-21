from django.urls import path
from . import views

app_name = 'label_printing'
urlpatterns = [
    path('', views.home, name='home'),
    path('preview/', views.preview, name='preview'),
]
