from django.urls import path
from . import views

app_name = "transaction_checks"
urlpatterns = [path("", views.overview, name="overview")]
