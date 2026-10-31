"""Runs pdfread.py in an isolated child process with a time limit."""
import json
import subprocess
import sys
from pathlib import Path

from django.conf import settings

WORKER = Path(__file__).with_name("pdfread.py")
FIELDS = ["sevis_id", "issue_date", "issue_reason", "education_level",
          "program_start", "program_end", "school", "travel_signatures", "country_of_citizenship",
          "admission_number", "earliest_admission", "start_of_classes", "school_code", "school_approval",
          "school_official", "school_official_title", "major_1", "major_1_cip", "major_2", "major_2_cip"]


def _blank(reason: str) -> dict:
    return {
        "text_layer": False, "scan": False, "pages": 0, "anchors": {},
        "work": {"value": "", "confidence": "missing", "reason": "Enter from the employment section", "auths": []},
        "fields": {f: {"value": "", "confidence": "missing", "reason": reason} for f in FIELDS},
        "checks": {k: {"status": "unknown", "detail": reason}
                   for k in ("dso_signature", "student_signature", "issue_date")},
    }


def read_pdf(data: bytes) -> dict:
    try:
        # -I: isolated mode, ignores environment variables and the current folder.
        proc = subprocess.run([sys.executable, "-I", str(WORKER), "--worker"], input=data,
                              capture_output=True, timeout=settings.STASH_EXTRACT_TIMEOUT)
        out = json.loads(proc.stdout or b"{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return _blank("Couldn't read this file automatically. Enter the fields by hand.")
    if "error" in out or "fields" not in out:
        return _blank("Couldn't read this file automatically. Enter the fields by hand.")
    return out


def read_image() -> dict:
    return _blank("Photo uploaded. Reading photos (OCR) isn't built yet, so enter the fields by hand.")


def render_first_page(data: bytes) -> dict | None:
    """Page 1 as an image, drawn in the same isolated process as reading."""
    try:
        proc = subprocess.run([sys.executable, "-I", str(WORKER), "--render"], input=data,
                              capture_output=True, timeout=settings.STASH_EXTRACT_TIMEOUT)
        out = json.loads(proc.stdout or b"{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    return None if "error" in out or "png" not in out else out
