from django.urls import path
from . import views

app_name = "smartmart_bulk"

urlpatterns = [
    path("", views.browse, name="browse"),
]
