from django.urls import path

from . import auth, views

urlpatterns = [
    path("pulse", views.pulse),
    path("live", views.live),
    path("auth/session", auth.session),
    path("auth/login", auth.sign_in),
    path("auth/logout", auth.sign_out),
]
