from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="documents"),
    path("upload", views.upload, name="upload"),
    path("signature.png", views.signature_image, name="signature_image"),
    path("<uuid:doc_id>/", views.detail, name="detail"),
    path("<uuid:doc_id>/review", views.review, name="review"),
    path("<uuid:doc_id>/file/<int:number>", views.file, name="file"),
    path("<uuid:doc_id>/sign", views.sign, name="sign"),
    path("<uuid:doc_id>/delete", views.delete, name="delete"),
]
