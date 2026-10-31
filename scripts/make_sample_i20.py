"""Makes FAKE I-20-style PDFs for testing and the demo. Every name, number and school is made up.
They follow the I-20's label-above-value layout, but they are not real forms.

    python scripts/make_sample_i20.py            -> sample_i20.pdf in this folder (fictional Manuel Sample)
"""
import sys
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

W, H = letter

# The default fake I-20. The tests rely on these exact values.
DEFAULT = {
    "sevis_id": "N0099887766", "surname": "SAMPLE", "given_name": "MANUEL",
    "country": "EXAMPLELAND", "reason": "CONTINUED ATTENDANCE",
    "admission_number": "123456789A1", "earliest_admission": date(2024, 7, 27), "start_of_classes": date(2024, 8, 26),
    "school": "Example State University", "school_address": "1 College Way, Exampletown",
    "school_code": "EXA214F00999000", "school_approval": date(2010, 3, 15),
    "dso": "Jordan Example", "dso_title": "PDSO",
    "level": "MASTER'S", "major_1": "Computer Science 11.0701", "major_2": "None 00.0000",
    "program_start": date(2024, 8, 26), "program_end": date(2026, 5, 15),
    "issue_date": date(2026, 4, 2), "place_issued": "EXAMPLETOWN, EX",
    # one authorization: (type text, time, start, end) or None
    "employment": ("POST-COMPLETION OPT", "FULL TIME", date(2026, 6, 15), date(2027, 6, 14)),
    "employer": None,  # {"name", "address", "start"} for an employer block on page 2
    "travel": [date(2026, 4, 20)],
}


def _d(d) -> str:
    return d.strftime("%m/%d/%Y") if d else ""


def label(c, x, y, text):
    c.setFont("Helvetica", 7)
    c.drawString(x, H - y, text)


def value(c, x, y, text):
    c.setFont("Helvetica", 10)
    c.drawString(x, H - y - 12, text)


def make_i20(path: Path, spec: dict | None = None, signed_by_student: bool = False):
    s = dict(DEFAULT, **(spec or {}))
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, H - 40, "SAMPLE ONLY - Certificate of Eligibility for Nonimmigrant Student Status")
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 56, f"SEVIS ID: {s['sevis_id']}")
    label(c, 430, 70, "CLASS OF ADMISSION"); value(c, 430, 70, "F-1")

    label(c, 40, 90, "SURNAME/PRIMARY NAME"); label(c, 250, 90, "GIVEN NAME")
    value(c, 40, 90, s["surname"]); value(c, 250, 90, s["given_name"])
    label(c, 40, 120, "COUNTRY OF CITIZENSHIP"); label(c, 250, 120, "FORM ISSUE REASON")
    value(c, 40, 120, s["country"]); value(c, 250, 120, s["reason"])

    label(c, 40, 140, "ADMISSION NUMBER"); label(c, 250, 140, "EARLIEST ADMISSION DATE"); label(c, 430, 140, "START OF CLASSES")
    value(c, 40, 140, s["admission_number"]); value(c, 250, 140, _d(s["earliest_admission"])); value(c, 430, 140, _d(s["start_of_classes"]))

    label(c, 40, 160, "SCHOOL NAME"); label(c, 320, 160, "SCHOOL ADDRESS")
    value(c, 40, 160, s["school"]); value(c, 320, 160, s["school_address"])

    label(c, 40, 180, "SCHOOL CODE AND APPROVAL DATE"); label(c, 320, 180, "SCHOOL OFFICIAL TO CONTACT UPON ARRIVAL")
    value(c, 40, 180, f"{s['school_code']}  {_d(s['school_approval'])}"); value(c, 320, 180, s["dso"])
    c.setFont("Helvetica", 10); c.drawString(320, H - 180 - 24, s["dso_title"])

    label(c, 40, 210, "EDUCATION LEVEL"); label(c, 250, 210, "MAJOR 1"); label(c, 430, 210, "MAJOR 2")
    value(c, 40, 210, s["level"]); value(c, 250, 210, s["major_1"]); value(c, 430, 210, s["major_2"])
    label(c, 40, 240, "PROGRAM START/END DATE")
    value(c, 40, 240, f"{_d(s['program_start'])} - {_d(s['program_end'])}")

    c.setFont("Helvetica-Bold", 9); c.drawString(40, H - 300, "SCHOOL ATTESTATION")
    label(c, 40, 320, "SIGNATURE OF:")
    # a drawn "signature" (curves) on the DSO line
    c.setLineWidth(1.2)
    p = c.beginPath(); p.moveTo(110, H - 318); p.curveTo(130, H - 300, 150, H - 330, 175, H - 312); p.curveTo(190, H - 305, 205, H - 322, 220, H - 314)
    c.drawPath(p, stroke=1, fill=0)
    c.setFont("Helvetica", 8); c.drawString(240, H - 318, f"{s['dso']}, {s['dso_title']}")
    label(c, 380, 320, "DATE ISSUED"); value(c, 380, 320, _d(s["issue_date"]))
    label(c, 480, 320, "PLACE ISSUED"); value(c, 480, 320, s["place_issued"])

    c.setFont("Helvetica-Bold", 9); c.drawString(40, H - 380, "STUDENT ATTESTATION")
    label(c, 40, 400, "SIGNATURE OF:")
    c.line(105, H - 402, 330, H - 402)
    label(c, 380, 400, "DATE")
    c.line(400, H - 402, 520, H - 402)
    if signed_by_student:
        p = c.beginPath(); p.moveTo(115, H - 398); p.curveTo(140, H - 385, 160, H - 405, 190, H - 392)
        c.drawPath(p, stroke=1, fill=0)
    c.showPage()

    y = 60
    c.setFont("Helvetica-Bold", 9); c.drawString(40, H - y, "EMPLOYMENT AUTHORIZATIONS")
    c.setFont("Helvetica", 9)
    if s["employment"]:
        kind, time, start, end = s["employment"]
        y += 16; c.drawString(40, H - y, f"{kind}  {time}  {_d(start)} - {_d(end)}")
        if s["employer"]:
            e = s["employer"]
            y += 14; c.drawString(40, H - y, f"EMPLOYER NAME: {e['name']}")
            y += 14; c.drawString(40, H - y, f"EMPLOYER ADDRESS: {e['address']}")
            if e.get("start"):
                y += 14; c.drawString(40, H - y, f"EMPLOYER START DATE: {_d(e['start'])}")
    y = max(y + 40, 140)
    c.setFont("Helvetica-Bold", 9); c.drawString(40, H - y, "TRAVEL ENDORSEMENT")
    c.setFont("Helvetica", 9)
    for d in s["travel"]:
        y += 20; c.drawString(40, H - y, f"Designated School Official: {s['dso']}   Date Issued: {_d(d)}")
    c.showPage()
    c.save()


def make(path: Path, signed_by_student: bool = False):
    """The default fake I-20 (Manuel Sample, a master's student on OPT)."""
    make_i20(path, None, signed_by_student)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("sample_i20.pdf")
    make(out)
    print(f"Wrote {out}")
