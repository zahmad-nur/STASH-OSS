"""Your saved signature (SIG-001). Each replacement becomes a new version."""
from .models import Document, Version


def saved_signature() -> Document | None:
    return Document.objects.filter(doc_type="SIG", status="saved").order_by("seq").first()


def store_signature(png: bytes) -> Document:
    sig = saved_signature()
    if not sig:
        sig = Document.create_next("SIG")
        sig.status = "saved"
        sig.set_data({"note": "Saved signature"})
        sig.save()
    Version.store(sig, png, "image/png", "upload")
    return sig
