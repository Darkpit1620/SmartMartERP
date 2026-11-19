from django.urls import path
from . import views

app_name = 'workforce'
urlpatterns = [
    path('', views.home, name='home'),
    path('attendance/<str:action>/', views.attendance_action, name='attendance_action'),
    path('leave/', views.my_leaves, name='my_leaves'),
    path('leave/new/', views.request_leave, name='request_leave'),
    path('leave/<int:pk>/cancel/', views.cancel_my_leave, name='cancel_leave'),
    path('team/', views.team, name='team'),
    path('team/attendance/', views.team_attendance, name='team_attendance'),
    path('team/leave/', views.team_leaves, name='team_leaves'),
    path('team/leave/<int:pk>/review/', views.review_leave, name='review_leave'),
]
