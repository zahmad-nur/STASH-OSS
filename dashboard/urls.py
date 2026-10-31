from django.urls import path

from . import views

urlpatterns = [
    path("", views.overview, name="overview"),
    path("stay", views.stay, name="stay"),
    path("lookup", views.lookup, name="lookup"),
    path("settings", views.settings_page, name="settings"),
]
