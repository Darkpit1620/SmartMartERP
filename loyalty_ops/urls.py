from django.urls import path
from . import views

app_name = 'loyalty_ops'
urlpatterns = [
    path('', views.home, name='home'),
    path('enroll/', views.enroll, name='enroll'),
    path('member/<int:pk>/', views.member_detail, name='member'),
    path('member/<int:pk>/sale/', views.link_receipt, name='link_receipt'),
    path('member/<int:pk>/toggle/', views.toggle_member, name='toggle_member'),
    path('member/<int:pk>/redeem/', views.redeem, name='redeem'),
    path('rewards/', views.rewards, name='rewards'),
    path('redemption/<int:pk>/review/', views.review, name='review'),
]
