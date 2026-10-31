"""python manage.py demo [--student manuel|priya|amara] [--no-server]

Loads a fake student into a separate demo data folder and starts STASH on
http://127.0.0.1:8001 (one port up from the real app, so both can run at once).
The demo folder is wiped and rebuilt every time. Your real data folder is never touched.
"""
import io
import shutil
import tempfile
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connections
from PIL import Image, ImageDraw

DEMO_PASSPHRASE = "stash-demo"


class Command(BaseCommand):
    help = "Try STASH with a fake student, in a throwaway demo folder."

    def add_arguments(self, parser):
        from documents.demo import STUDENTS
        parser.add_argument("--student", choices=sorted(STUDENTS), default="manuel",
                            help="manuel: CPT, OPT and STEM OPT; priya: master's on CPT now; amara: new degree after OPT")
        parser.add_argument("--no-server", action="store_true", help="Load the data but don't start the server")

    def handle(self, *args, **opts):
        if not getattr(settings, "STASH_DEMO", False) or "Demo" not in str(settings.DATA_DIR):
            raise CommandError("Run the demo with `python manage.py demo`, which uses its own data folder.")
        self._reset(Path(settings.DATA_DIR))
        call_command("migrate", verbosity=0)
        self._clear_rows()
        student = self._load(opts["student"])
        self.stdout.write(self.style.SUCCESS(
            f"\nDemo ready: {student['name']} ({len(student['i20s'])} fake I-20s)."
            f"\nData folder (deleted and rebuilt on every run): {settings.DATA_DIR}"
            f"\nOpen http://127.0.0.1:8001 and unlock with the passphrase: {DEMO_PASSPHRASE}\n"))
        if not opts["no_server"]:
            call_command("runserver", "127.0.0.1:8001", use_reloader=False)

    def _reset(self, folder: Path):
        connections.close_all()
        for name in ("stash.sqlite3", "keys.json"):
            (folder / name).unlink(missing_ok=True)
        shutil.rmtree(folder / "files", ignore_errors=True)
        (folder / "files").mkdir(parents=True, exist_ok=True)

    def _clear_rows(self):
        """Leftover rows from an earlier demo can't be read with the new demo key."""
        from documents.models import Document
        from vault.models import Profile
        Document.objects.all().delete()
        Profile.objects.all().delete()

    def _load(self, key: str) -> dict:
        import importlib.util

        from documents import signing
        from documents.demo import STUDENTS
        from documents.extract import read_pdf
        from documents.models import Document, Version
        from documents.signatures import store_signature
        from vault import keystore
        from vault.models import Profile

        spec = importlib.util.spec_from_file_location("mk", Path(settings.BASE_DIR) / "scripts" / "make_sample_i20.py")
        mk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mk)

        keystore.setup(DEMO_PASSPHRASE)  # unlocks this process while loading
        today = date.today()
        student = STUDENTS[key](today)
        Profile.save_data({"name": student["name"], "country": student["country"], "greeting_mode": "auto",
                           "native_script": True})
        tmp = Path(tempfile.mkdtemp())
        for n, i20 in enumerate(student["i20s"], start=1):
            extra = {k: i20.pop(k) for k in ("_wrong", "_sign") if k in i20}
            path = tmp / f"i20-{n}.pdf"
            mk.make_i20(path, i20)
            pdf = path.read_bytes()
            doc = Document.create_next("I20")
            Version.store(doc, pdf, "application/pdf", "upload")
            result = read_pdf(pdf)
            fields = result["fields"]
            for name, (correct, note) in extra.get("_wrong", {}).items():
                fields[name].update(doc_wrong=True, corrected=correct.isoformat(), note=note)
            doc.set_data({"fields": fields, "checks": result["checks"], "anchors": result.get("anchors", {}),
                          "work": result.get("work"), "source": {"text_layer": True, "scan": False, "mime": "application/pdf"}})
            doc.status = "saved"
            doc.save()
            if extra.get("_sign"):
                self._sign(doc, pdf, result, i20["issue_date"], signing, store_signature, Version)
        shutil.rmtree(tmp, ignore_errors=True)
        keystore.lock()
        return student

    def _sign(self, doc, pdf, result, issued, signing, store_signature, Version):
        """Signs one I-20 in STASH, so the demo shows a v2 signed copy next to the original."""
        img = Image.new("RGBA", (600, 170), (0, 0, 0, 0))
        ImageDraw.Draw(img).line([(30, 120), (140, 40), (220, 130), (330, 60), (420, 110), (570, 50)],
                                 fill=(25, 25, 25, 255), width=6, joint="curve")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()
        store_signature(png)
        w, h = result.get("page1_size", (612.0, 792.0))
        place = signing.default_placement(result.get("anchors", {}).get("student_signature"), w, h)
        Version.store(doc, signing.stamp(pdf, png, place, issued), "application/pdf", "signed")
        data = doc.get_data()
        data["checks"]["student_signature"] = {"status": "found", "detail": "Signed in STASH", "signed_in_app": True}
        doc.set_data(data)
        doc.save()
