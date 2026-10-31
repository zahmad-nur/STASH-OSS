"""End-to-end test of the I-20 flow against a FAKE I-20.

    python manage.py test tests
"""
import base64
import io
import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase, override_settings
from PIL import Image, ImageDraw

from documents.models import Document, Version
from vault import keystore

ROOT = Path(__file__).resolve().parent.parent


def sample_pdf(signed=False) -> bytes:
    import importlib.util
    spec = importlib.util.spec_from_file_location("mk", ROOT / "scripts" / "make_sample_i20.py")
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    tmp = Path(tempfile.mkdtemp()) / "s.pdf"
    mk.make(tmp, signed_by_student=signed)
    return tmp.read_bytes()


def drawn_signature() -> str:
    img = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(40, 150), (200, 60), (360, 140), (560, 70)], fill=(20, 20, 20, 255), width=5)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class FlowTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "files").mkdir()
        self.override = override_settings(DATA_DIR=self.tmp)
        self.override.enable()
        keystore.lock()
        self.c = Client(enforce_csrf_checks=False)

    def tearDown(self):
        keystore.lock()
        self.override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _setup_vault(self):
        r = self.c.post("/setup", {"passphrase": "correct horse battery", "confirm": "correct horse battery",
                                   "name": "Manuel", "greeting": "Bienvenido"})
        self.assertEqual(r.status_code, 200)
        return re.search(r'class="recovery">([A-Z0-9-]+)<', r.content.decode()).group(1)

    def test_full_flow(self):
        # locked app sends you to setup
        self.assertEqual(self.c.get("/").url, "/setup")
        recovery = self._setup_vault()
        self.assertIn("Bienvenido</bdi>, Manuel", self.c.get("/").content.decode())

        # upload -> review with extracted fields
        pdf = sample_pdf()
        r = self.c.post("/documents/upload", {"file": io.BytesIO(pdf)}, follow=True)
        html = r.content.decode()
        self.assertIn("Check what we read from I20-001", html)
        self.assertIn('value="N0099887766"', html)
        self.assertIn('value="2026-05-15"', html)
        doc = Document.objects.get(doc_type="I20", seq=1)
        self.assertEqual(doc.status, "draft")

        # nothing readable on disk: file and database are encrypted
        stored = next((self.tmp / "files").iterdir()).read_bytes()
        self.assertNotIn(b"%PDF", stored)
        self.assertNotIn(b"N0099887766", (self.tmp / "stash.sqlite3").read_bytes() if (self.tmp / "stash.sqlite3").exists() else b"")
        self.assertNotIn(b"N0099887766", bytes(doc.data_enc))

        # review: correct a field the DSO got wrong, then save
        fields = {"sevis_id": "N0099887766", "issue_date": "2026-04-02", "issue_reason": "CONTINUED ATTENDANCE",
                  "education_level": "MASTER'S", "program_start": "2024-08-26", "program_end": "2026-05-15",
                  "school": "Example State University", "travel_signatures": "2026-04-20", "country_of_citizenship": "PAKISTAN",
                  "school__wrong": "on", "school__corrected": "Example State Univ.", "school__note": "test note",
                  "action": "save"}
        r = self.c.post(f"/documents/{doc.id}/review", fields, follow=True)
        self.assertIn("Saved. I20-001 is stored encrypted on this computer.", r.content.decode())
        r = self.c.post(f"/documents/{doc.id}/review", fields, follow=True)
        self.assertIn("Changes saved to I20-001.", r.content.decode())
        doc.refresh_from_db()
        self.assertEqual(doc.status, "saved")
        self.assertEqual(doc.get_data()["fields"]["school"]["value"], "Example State University")  # printed kept

        # dashboard pages
        html = self.c.get("/").content.decode()
        self.assertIn("On OPT", html)  # the sample lists OPT from 15 Jun 2026
        self.assertIn("20 Apr 2027", html)  # travel signature + 1 year
        self.assertIn("My Stay in the US", self.c.get("/stay").content.decode())
        html = self.c.get("/lookup?date=2025-06-01").content.decode()
        self.assertIn("No I-20 issued yet", html)
        html = self.c.get("/lookup?date=2026-04-25").content.decode()
        self.assertIn("I20-001", html)
        self.assertIn("Valid: signed 20 Apr 2026", html)

        # duplicate upload is caught
        r = self.c.post("/documents/upload", {"file": io.BytesIO(pdf)})
        self.assertIn("dup=1", r.url)
        self.assertEqual(Document.objects.filter(doc_type="I20").count(), 1)

        # sign -> v2, original v1 untouched
        r = self.c.post(f"/documents/{doc.id}/sign", {"signature": drawn_signature()})
        self.assertEqual(r.status_code, 302)
        versions = list(doc.versions.order_by("number"))
        self.assertEqual([v.kind for v in versions], ["upload", "signed"])
        self.assertEqual(versions[0].read(), pdf)
        self.assertTrue(versions[1].read().startswith(b"%PDF"))
        self.assertTrue(Document.objects.filter(doc_type="SIG", seq=1).exists())
        html = self.c.get(f"/documents/{doc.id}/?v=1").content.decode()
        self.assertIn("v1 of 2", html)
        # signed copy now reads as signed
        from documents.pdfread import extract
        self.assertEqual(extract(versions[1].read())["checks"]["student_signature"]["status"], "found")
        r = self.c.get(f"/documents/{doc.id}/file/2")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertEqual(r["Cache-Control"], "no-store")

        # lock -> everything redirects; wrong passphrase fails; right one works
        self.c.post("/lock")
        self.assertEqual(self.c.get("/").url, "/unlock")
        self.assertEqual(self.c.get(f"/documents/{doc.id}/file/1").url, "/unlock")
        r = self.c.post("/unlock", {"passphrase": "wrong passphrase!!"})
        self.assertIn("That passphrase", r.content.decode())
        self.assertEqual(self.c.post("/unlock", {"passphrase": "correct horse battery"}).url, "/")
        self.assertEqual(self.c.get("/").status_code, 200)

        # recovery key sets a new passphrase
        self.c.post("/lock")
        r = self.c.post("/recover", {"recovery": recovery.lower(), "passphrase": "new passphrase here", "confirm": "new passphrase here"})
        self.assertEqual(r.url, "/")
        self.c.post("/lock")
        self.assertEqual(self.c.post("/unlock", {"passphrase": "new passphrase here"}).url, "/")

        # another browser without the unlock cookie can't read anything
        other = Client()
        self.assertEqual(other.get("/").url, "/unlock")

        # delete removes encrypted files
        self.c.post(f"/documents/{doc.id}/delete")
        self.assertFalse(Document.objects.filter(id=doc.id).exists())

    def test_cancel_deletes_upload(self):
        self._setup_vault()
        self.c.post("/documents/upload", {"file": io.BytesIO(sample_pdf())})
        doc = Document.objects.get(doc_type="I20")
        self.c.post(f"/documents/{doc.id}/review", {"action": "cancel"})
        self.assertFalse(Document.objects.exists())
        self.assertEqual(list((self.tmp / "files").iterdir()), [])

    def test_rejects_non_local_and_bad_files(self):
        self._setup_vault()
        self.assertEqual(Client(REMOTE_ADDR="192.168.1.5").get("/").status_code, 403)
        r = self.c.post("/documents/upload", {"file": io.BytesIO(b"<html>not a pdf</html>")})
        self.assertIn("unsupported", r.url)

    def test_data_dir_inside_repo_refused(self):
        from django.core.exceptions import ImproperlyConfigured
        from vault.paths import data_dir
        import os
        os.environ["STASH_DATA_DIR"] = str(ROOT / "data")
        try:
            with self.assertRaises(ImproperlyConfigured):
                data_dir(ROOT)
        finally:
            os.environ.pop("STASH_DATA_DIR")


class FeedbackTest(FlowTest):
    """Behaviour added after the first real-document test."""

    def _save_sample(self, signed=False):
        self.c.post("/documents/upload", {"file": io.BytesIO(sample_pdf(signed=signed))})
        doc = Document.objects.filter(doc_type="I20").order_by("-seq").first()
        data = {name: f.get("value", "") for name, f in doc.get_data()["fields"].items()}
        data["action"] = "save"
        self.c.post(f"/documents/{doc.id}/review", data)
        doc.refresh_from_db()
        return doc

    def test_greeting_follows_citizenship(self):
        self.c.post("/setup", {"passphrase": "correct horse battery", "confirm": "correct horse battery", "name": "Manuel"})
        self.assertIn("Welcome</bdi>, Manuel", self.c.get("/").content.decode())
        doc = self._save_sample()
        self.assertEqual(doc.get_data()["fields"]["country_of_citizenship"]["value"], "EXAMPLELAND")
        r = self.c.post(f"/documents/{doc.id}/review", {**{k: v.get("value", "") for k, v in doc.get_data()["fields"].items()},
                                                       "country_of_citizenship": "PAKISTAN", "action": "save"})
        html = self.c.get("/").content.decode()
        self.assertIn("خوش آمدید</bdi>, Manuel", html)
        self.assertIn('lang="ur" dir="rtl"', html)
        self.c.post("/settings", {"action": "profile", "name": "Manuel", "greeting_mode": "auto"})  # script off
        self.assertIn("Khush aamdeed</bdi>, Manuel", self.c.get("/").content.decode())
        # a chosen greeting wins
        self.c.post("/settings", {"action": "profile", "name": "Manuel", "greeting_mode": "custom", "greeting": "Hey"})
        self.assertIn("Hey</bdi>, Manuel", self.c.get("/").content.decode())

    def test_signature_upload_and_placement(self):
        self._setup_vault()
        # a JPG photo of a signature on white paper
        img = Image.new("RGB", (800, 300), "white")
        ImageDraw.Draw(img).line([(60, 220), (300, 80), (520, 200), (740, 90)], fill=(30, 30, 30), width=9)
        buf = io.BytesIO(); img.save(buf, format="JPEG")
        self.c.post("/settings", {"action": "upload_sig", "file": io.BytesIO(buf.getvalue())})
        sig = Document.objects.get(doc_type="SIG")
        png = Image.open(io.BytesIO(sig.latest_version().read()))
        self.assertEqual(png.mode, "RGBA")
        self.assertEqual(png.getpixel((0, 0))[3], 0)  # paper became transparent

        doc = self._save_sample()
        html = self.c.get(f"/documents/{doc.id}/sign").content.decode()
        self.assertIn('id="placer"', html)
        self.assertIn("data:image/png;base64,", html)  # page 1 rendered for placement
        r = self.c.post(f"/documents/{doc.id}/sign", {"source": "saved", "sig_x": "0.2", "sig_y": "0.45",
                                                     "sig_w": "0.25", "date_x": "0.65", "date_y": "0.48", "date": "2026-10-01"})
        self.assertIn("signed=1", r.url)
        html = self.c.get(r.url).content.decode()
        self.assertIn("Back to Overview", html)
        self.assertIn("Redo signature", html)
        from documents.pdfread import extract
        signed = doc.versions.order_by("-number").first().read()
        import pdfplumber
        with pdfplumber.open(io.BytesIO(signed)) as pdf:
            self.assertIn("10/01/2026", pdf.pages[0].extract_text())

    def test_already_signed_needs_no_signature(self):
        self._setup_vault()
        doc = self._save_sample(signed=True)
        self.assertEqual(doc.get_data()["checks"]["student_signature"]["status"], "found")
        html = self.c.get(f"/documents/{doc.id}/").content.decode()
        self.assertNotIn("Sign this I-20", html)
        self.assertIn("already on this I-20", html)


class WorkAuthTest(FeedbackTest):
    BASE = {"sevis_id": "N0099887766", "issue_date": "2026-04-02", "issue_reason": "CONTINUED ATTENDANCE",
            "education_level": "MASTER'S", "program_start": "2024-08-26", "program_end": "2026-05-15",
            "school": "Example State University", "travel_signatures": "2026-04-20",
            "country_of_citizenship": "EXAMPLELAND", "action": "save"}

    def _row(self, **kw):
        keys = ["type", "start", "end", "employer_type", "employer_name", "employer_start", "employer_end", "city", "state"]
        return {f"work_{k}": kw.get(k, "") for k in keys}

    def test_work_authorization_fields(self):
        self._setup_vault()
        self.c.post("/documents/upload", {"file": io.BytesIO(sample_pdf())})
        doc = Document.objects.get(doc_type="I20", seq=1)
        html = self.c.get(f"/documents/{doc.id}/review").content.decode()
        self.assertIn('value="yes" checked', html)
        self.assertIn('<option value="OPT" selected>', html)
        self.assertIn('value="2027-06-14"', html)

        post = dict(self.BASE, work_auth="yes", **self._row(
            type="OPT", start="2026-06-15", end="2027-06-14", employer_type="OPT",
            employer_name="Example Corp", employer_start="2026-07-01", city="Springfield", state="IL"))
        self.c.post(f"/documents/{doc.id}/review", post)
        work = Document.objects.get(id=doc.id).get_data()["work"]
        self.assertEqual(len(work["auths"]), 1)
        self.assertEqual(work["auths"][0]["employer_name"], "Example Corp")
        self.assertNotIn(b"Example Corp", bytes(Document.objects.get(id=doc.id).data_enc))  # encrypted

        detail = self.c.get(f"/documents/{doc.id}/").content.decode()
        self.assertIn("Example Corp · OPT · Springfield, IL", detail)
        overview = self.c.get("/").content.decode()
        self.assertIn("OPT – Work Authorization Ends", overview)
        self.assertIn("Example Corp", overview)
        self.assertNotIn("From I20-001", overview)
        stay = self.c.get("/stay").content.decode()
        self.assertIn("Grace period · 15 May 2026 – 15 Jun 2026", stay)
        self.assertIn("OPT · 15 Jun 2026 – 14 Jun 2027", stay)
        self.assertIn("Example Corp", self.c.get("/lookup?date=2026-08-01").content.decode())

        # No drops every employment field, even ones still filled in on the form
        self.c.post(f"/documents/{doc.id}/review", dict(post, work_auth="no"))
        work = Document.objects.get(id=doc.id).get_data()["work"]
        self.assertEqual((work["value"], work["auths"]), ("no", []))
        self.assertNotIn("Work Authorization Ends", self.c.get("/").content.decode())

    def test_older_i20s_get_work_info_once(self):
        self._setup_vault()
        self.c.post("/documents/upload", {"file": io.BytesIO(sample_pdf())})
        doc = Document.objects.get(doc_type="I20", seq=1)
        self.c.post(f"/documents/{doc.id}/review", self.BASE)  # saved without the employment section
        data = doc.get_data() if False else Document.objects.get(id=doc.id).get_data()
        data.pop("work", None)  # as if saved before employment fields existed
        doc = Document.objects.get(id=doc.id); doc.set_data(data); doc.save()
        self.assertIn("OPT – Work Authorization Ends", self.c.get("/").content.decode())
        work = Document.objects.get(id=doc.id).get_data()["work"]
        self.assertEqual((work["confidence"], work["auths"][0]["type"]), ("check", "OPT"))
        self.assertEqual(Document.objects.get(id=doc.id).get_data()["fields"]["school"]["value"], "Example State University")


class OverviewCardsTest(WorkAuthTest):
    def test_cards_and_documents_tab(self):
        self._setup_vault()
        self.c.post("/documents/upload", {"file": io.BytesIO(sample_pdf())})
        doc = Document.objects.get(doc_type="I20", seq=1)
        review = self.c.get(f"/documents/{doc.id}/review").content.decode()
        self.assertIn('value="EXA214F00999000"', review)
        self.assertIn('value="11.0701"', review)
        self.c.post(f"/documents/{doc.id}/review", self.BASE)  # base fields only: page-1 details kept as read

        html = self.c.get("/").content.decode()
        self.assertIn("SCHOOL CONTACT", html)
        self.assertIn("Jordan Example", html)
        self.assertIn("PDSO · Example State University", html)
        self.assertIn("FIELD OF STUDY · MASTER", html)
        self.assertIn("CIP 11.0701 · Major 1", html)
        self.assertNotIn("Major 2", html)  # "None 00.0000" on the I-20 counts as blank
        self.assertIn('data-full="N0099887766"', html)
        self.assertIn("N00••••7766", html)
        self.assertIn("Your I-94 number", html)
        self.assertIn("Approved 15 Mar 2010", html)
        self.assertIn("Earliest admission", html)
        self.assertNotIn(">Employer<", html)  # no employer printed on the sample
        self.assertIn("Continued attendance", html)  # Description column

        tab = self.c.get("/documents/").content.decode()
        self.assertIn("I-20s · 1", tab)
        self.assertNotIn('id="i94s"', tab)  # I-94s aren't in this release
        self.assertIn("No signature saved yet", tab)

    def test_older_i20s_get_page1_details_once(self):
        self._setup_vault()
        self.c.post("/documents/upload", {"file": io.BytesIO(sample_pdf())})
        doc = Document.objects.get(doc_type="I20", seq=1)
        self.c.post(f"/documents/{doc.id}/review", self.BASE)
        doc = Document.objects.get(id=doc.id)
        data = doc.get_data()
        for k in ["school_code", "school_official", "major_1", "major_1_cip"]:
            data["fields"].pop(k)
        doc.set_data(data); doc.save()
        self.assertIn("Jordan Example", self.c.get("/").content.decode())
        f = Document.objects.get(id=doc.id).get_data()["fields"]
        self.assertEqual((f["school_code"]["value"], f["school_code"]["confidence"]), ("EXA214F00999000", "check"))


class StayTest(WorkAuthTest):
    def test_travel_signatures_not_on_stay_timeline(self):
        self._setup_vault()
        self.c.post("/documents/upload", {"file": io.BytesIO(sample_pdf())})
        doc = Document.objects.get(doc_type="I20", seq=1)
        self.c.post(f"/documents/{doc.id}/review", dict(self.BASE, travel_signatures="2024-05-10", work_auth="no"))
        html = self.c.get("/stay").content.decode()
        self.assertNotIn("Travel signature", html)
        self.assertNotIn("Before your program", html)
        self.assertIn("26 Aug 2024 – ", html)  # starts at the program start


class NewProgramTest(WorkAuthTest):
    def _save(self, pdf, **fields):
        self.c.post("/documents/upload", {"file": io.BytesIO(pdf)})
        doc = Document.objects.filter(doc_type="I20").order_by("-seq").first()
        self.c.post(f"/documents/{doc.id}/review", dict(self.BASE, **fields))
        return doc

    def _two_programs(self, master_start):
        self._setup_vault()
        self._save(sample_pdf(), issue_date="2025-04-02", education_level="BACHELOR'S",
                   program_start="2021-08-20", program_end="2025-05-10", travel_signatures="2025-04-20",
                   work_auth="yes", **self._row(type="STEM OPT", start="2025-06-15", end="2027-06-14",
                                                employer_name="Example Corp B"))
        self._save(sample_pdf(signed=True), issue_date="2026-06-01", program_start=master_start,
                   program_end="2028-05-15", travel_signatures="", work_auth="no")

    def test_new_program_started_ends_old_authorization(self):
        self._two_programs("2026-08-20")  # already started (today is later)
        html = self.c.get("/").content.decode()
        self.assertNotIn("Work Authorization Ends", html)
        self.assertNotIn("On STEM OPT", html)
        self.assertIn("Enrolled", html)
        self.assertIn("No travel signature on your current I-20", html)
        self.assertNotIn("20 Apr 2026", html)  # the old I-20's signature doesn't carry over
        stay = self.c.get("/stay").content.decode()
        self.assertIn("STEM OPT · 15 Jun 2025 – 20 Aug 2026 (ended when your next program started", stay)

    def test_new_i20_before_its_program_starts(self):
        self._two_programs("2099-08-20")  # issued, but the new program hasn't started
        html = self.c.get("/").content.decode()
        self.assertIn("On STEM OPT", html)
        self.assertIn("STEM OPT – Work Authorization Ends", html)


class ReadingTest(TestCase):
    def test_label_words_inside_a_value(self):
        # "CHANGE OF EDUCATION LEVEL" must not be mistaken for the EDUCATION LEVEL label
        import importlib.util
        from documents.pdfread import extract
        spec = importlib.util.spec_from_file_location("mk", ROOT / "scripts" / "make_sample_i20.py")
        mk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mk)
        tmp = Path(tempfile.mkdtemp()) / "c.pdf"
        mk.make_i20(tmp, {"reason": "CHANGE OF EDUCATION LEVEL"})
        f = extract(tmp.read_bytes())["fields"]
        self.assertEqual(f["issue_reason"]["value"], "CHANGE OF EDUCATION LEVEL")
        self.assertEqual(f["education_level"]["value"], "MASTER'S")


class DemoTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "STASH Demo"
        (self.tmp / "files").mkdir(parents=True)
        self.override = override_settings(DATA_DIR=self.tmp, STASH_DEMO=True)
        self.override.enable()
        keystore.lock()

    def tearDown(self):
        keystore.lock()
        self.override.disable()
        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def _demo(self, student):
        from django.core.management import call_command
        call_command("demo", student=student, no_server=True, stdout=io.StringIO())
        c = Client()
        self.assertEqual(c.post("/unlock", {"passphrase": "stash-demo"}).url, "/")
        return c

    def test_manuel(self):
        c = self._demo("manuel")
        html = c.get("/").content.decode()
        self.assertIn('<div class="demo-banner" role="note">Demo mode</div>', html)
        self.assertIn("On STEM OPT", html)
        self.assertIn("Hola</bdi>, Manuel", html)
        self.assertEqual(Document.objects.filter(doc_type="I20").count(), 5)
        self.assertIn("1 flag", c.get("/documents/").content.decode())  # the DSO typo on the first I-20
        self.assertTrue(Version.objects.filter(kind="signed").exists())

    def test_priya_and_amara(self):
        self.assertIn("CPT", self._demo("priya").get("/").content.decode())
        html = self._demo("amara").get("/").content.decode()
        self.assertIn("Enrolled", html)
        self.assertIn("Master&#x27;s at Example School of Business", html)
        self.assertIn("No travel signature on your current I-20", html)
        self.assertNotIn("OPT – Work Authorization Ends", html)

    def test_demo_refuses_real_data_folder(self):
        from django.core.management import CommandError, call_command
        with override_settings(DATA_DIR=Path(tempfile.mkdtemp()) / "STASH"):
            with self.assertRaises(CommandError):
                call_command("demo", no_server=True, stdout=io.StringIO())
