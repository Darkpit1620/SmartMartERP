from django.urls import path
from . import views

app_name = "pricing_portal"

urlpatterns = [
    path("", views.pricing_home, name="home"),
    path("export/", views.download_template, name="export"),
]
