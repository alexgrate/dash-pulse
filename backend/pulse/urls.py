from django.urls import path

from . import accounts, auth, explore, views

urlpatterns = [
    path("pulse", views.pulse),
    path("live", views.live),
    path("explore/transactions", explore.transactions),
    path("explore/transactions/<int:tx_id>", explore.transaction),
    path("explore/onboarding", explore.onboarding),
    path("explore/people", explore.people),
    path("explore/signup-history", explore.signup_history),
    path("explore/money-in", explore.money_in),
    path("auth/session", auth.session),
    path("auth/login", auth.sign_in),
    path("auth/logout", auth.sign_out),
    path("auth/forgot", accounts.forgot),
    path("auth/check-link", accounts.check_link),
    path("auth/set-password", accounts.set_password),
]
