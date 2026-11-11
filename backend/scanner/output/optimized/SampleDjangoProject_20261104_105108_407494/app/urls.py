from django.urls import path, re_path
from app import views


urlpatterns = [
    path("dashboard/", views.dashboard),
    re_path(r".*", views.profile, name="view"),
]
