from django.urls import path
from . import views

urlpatterns = [
    path("pulse", views.pulse),
]