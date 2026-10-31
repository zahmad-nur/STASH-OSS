import uuid

from django.db import models, transaction
from django.db.models import Max

from vault import secure

TYPE_LABELS = {"I20": "I-20", "SIG": "Signature"}


class Document(models.Model):
    """One piece of paper. A reissued I-20 is a new Document; a signed copy is a new Version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # hidden primary key
    doc_type = models.CharField(max_length=8)
    seq = models.PositiveIntegerField()
    status = models.CharField(max_length=10, default="draft")  # draft | saved
    created_at = models.DateTimeField(auto_now_add=True)
    data_enc = models.BinaryField(null=True)  # fields, corrections, checks: all encrypted

    class Meta:
        unique_together = [("doc_type", "seq")]
        ordering = ["doc_type", "seq"]

    @property
    def display_id(self) -> str:
        return f"{self.doc_type}-{self.seq:03d}"

    @property
    def type_label(self) -> str:
        return TYPE_LABELS.get(self.doc_type, self.doc_type)

    def _aad(self) -> bytes:
        return b"doc:" + self.id.bytes

    def get_data(self) -> dict:
        return secure.decrypt_json(self.data_enc, self._aad())

    def set_data(self, data: dict) -> None:
        self.data_enc = secure.encrypt_json(data, self._aad())

    @classmethod
    def create_next(cls, doc_type: str) -> "Document":
        with transaction.atomic():
            last = cls.objects.filter(doc_type=doc_type).aggregate(m=Max("seq"))["m"] or 0
            return cls.objects.create(doc_type=doc_type, seq=last + 1)

    def latest_version(self):
        return self.versions.order_by("-number").first()

    def remove(self) -> None:
        for v in self.versions.all():
            secure.delete_file(v.blob_name)
        self.delete()


class Version(models.Model):
    """v1 is the upload. Later versions (e.g. signed) never change earlier ones."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    kind = models.CharField(max_length=10)  # upload | signed
    mime = models.CharField(max_length=40)
    size = models.PositiveIntegerField()
    blob_name = models.CharField(max_length=40)
    fingerprint = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("document", "number")]
        ordering = ["number"]

    def _aad(self) -> bytes:
        return b"ver:" + self.id.bytes

    @classmethod
    def store(cls, document: Document, data: bytes, mime: str, kind: str) -> "Version":
        number = (document.versions.aggregate(m=Max("number"))["m"] or 0) + 1
        v = cls(document=document, number=number, kind=kind, mime=mime, size=len(data),
                fingerprint=secure.fingerprint(data))
        v.blob_name = secure.put_file(data, v._aad())
        v.save()
        return v

    def read(self) -> bytes:
        return secure.get_file(self.blob_name, self._aad())
