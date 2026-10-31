from django.urls import path

from . import views

urlpatterns = [
    path("setup", views.setup, name="setup"),
    path("unlock", views.unlock, name="unlock"),
    path("recover", views.recover, name="recover"),
    path("lock", views.lock, name="lock"),
]
