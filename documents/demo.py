"""Fake students for demo mode. Every name, number, school and employer here is made up.

Dates are worked out from today, so the demo always looks current: someone is mid-STEM OPT,
someone is on CPT right now, and someone has just started a new degree.
"""
from datetime import date, timedelta

SCHOOL = {"school": "Example State University", "school_address": "1 College Way, Exampletown",
          "school_code": "EXA214F00999000", "school_approval": date(2010, 3, 15),
          "dso": "Jordan Example", "dso_title": "PDSO", "place_issued": "EXAMPLETOWN, EX"}
TECH = {"school": "Example Institute of Technology", "school_address": "200 Sample Ave, Testville",
        "school_code": "EXT214F00888000", "school_approval": date(2004, 9, 1),
        "dso": "Casey Placeholder", "dso_title": "DSO", "place_issued": "TESTVILLE, TS"}
BUSINESS = {"school": "Example School of Business", "school_address": "5 Ledger Rd, Mocktown",
            "school_code": "EXB214F00777000", "school_approval": date(1998, 1, 20),
            "dso": "Riley Fictional", "dso_title": "PDSO", "place_issued": "MOCKTOWN, MK"}


def _last(month: int, day: int, today: date) -> int:
    """Year of the most recent month/day on or before today."""
    return today.year if (today.month, today.day) >= (month, day) else today.year - 1


def manuel(today: date) -> dict:
    """Bachelor's, CPT, OPT, then STEM OPT reissued after a worksite move. One DSO typo."""
    a = _last(6, 15, today)  # STEM OPT started on 15 Jun of this year
    base = dict(SCHOOL, sevis_id="N0011223344", surname="SAMPLE", given_name="MANUEL", country="MEXICO",
                level="BACHELOR'S", major_1="Computer Science 11.0701", major_2="Mathematics 27.0101",
                program_start=date(a - 5, 8, 20), program_end=date(a - 1, 5, 10),
                earliest_admission=date(a - 5, 7, 21), start_of_classes=date(a - 5, 8, 20),
                admission_number="987654321A1")
    stem_issued = date(a, 4, 1)
    move_issued = stem_issued + max((today - stem_issued) // 2, timedelta(days=1))
    employer = {"name": "Example Corp", "address": "10 Market St, Denver, CO 80202", "start": date(a - 1, 7, 1)}
    moved = dict(employer, address="77 Harbor Rd, Portland, OR 97204")
    return {
        "name": "Manuel", "country": "MEXICO",
        "i20s": [
            dict(base, reason="INITIAL ATTENDANCE", issue_date=date(a - 5, 4, 2), employment=None,
                 # the DSO wrote last year instead of this year: a real kind of mistake
                 travel=[date(a - 5, 12, 1)], _wrong={"travel_signatures": (date(a - 4, 12, 1), "DSO wrote the wrong year")}),
            dict(base, reason="CONTINUED ATTENDANCE", issue_date=date(a - 2, 5, 1),
                 employment=("CURRICULAR PRACTICAL TRAINING", "FULL TIME", date(a - 2, 6, 1), date(a - 2, 8, 15)),
                 employer={"name": "Example Labs", "address": "3 Lab Ln, Austin, TX 78701", "start": date(a - 2, 6, 1)},
                 travel=[]),
            dict(base, reason="CONTINUED ATTENDANCE", issue_date=date(a - 1, 3, 10),
                 employment=("POST-COMPLETION OPT", "FULL TIME", date(a - 1, 6, 15), date(a, 6, 14)),
                 employer=None, travel=[date(a - 1, 3, 20)]),
            dict(base, reason="CONTINUED ATTENDANCE", issue_date=stem_issued,
                 employment=("STEM OPT EXTENSION", "FULL TIME", date(a, 6, 15), date(a + 2, 6, 14)),
                 employer=employer, travel=[stem_issued + timedelta(days=9)], _sign=True),
            dict(base, reason="CONTINUED ATTENDANCE", issue_date=move_issued,
                 employment=("STEM OPT EXTENSION", "FULL TIME", date(a, 6, 15), date(a + 2, 6, 14)),
                 employer=moved, travel=[min(move_issued + timedelta(days=5), today)]),
        ],
    }


def priya(today: date) -> dict:
    """Master's student on CPT right now."""
    b = today.year - 1 if today.month >= 8 else today.year - 2  # program started 8 to 20 months ago
    start, end = date(b, 8, 25), date(b + 2, 12, 15)
    cpt_start = today - timedelta(days=30)
    base = dict(TECH, sevis_id="N0055667788", surname="EXAMPLE", given_name="PRIYA", country="INDIA",
                level="MASTER'S", major_1="Data Science 30.7001", major_2="None 00.0000",
                program_start=start, program_end=end, earliest_admission=start - timedelta(days=30),
                start_of_classes=start, admission_number="")
    return {
        "name": "Priya", "country": "INDIA",
        "i20s": [
            dict(base, reason="INITIAL ATTENDANCE", issue_date=date(b, 4, 15), employment=None,
                 travel=[date(b, 12, 5)]),
            dict(base, reason="CONTINUED ATTENDANCE", issue_date=cpt_start - timedelta(days=10),
                 employment=("CURRICULAR PRACTICAL TRAINING", "PART TIME", cpt_start, today + timedelta(days=60)),
                 employer={"name": "Sample Analytics LLC", "address": "9 Wacker Dr, Chicago, IL 60601", "start": cpt_start},
                 travel=[cpt_start - timedelta(days=5)]),
        ],
    }


def amara(today: date) -> dict:
    """Bachelor's, then OPT, then a master's that started before OPT ran out (change of level)."""
    c = _last(8, 20, today)  # the master's started on 20 Aug of this year
    bach = dict(SCHOOL, sevis_id="N0099001122", surname="TEST", given_name="AMARA", country="NIGERIA",
                level="BACHELOR'S", major_1="Economics 45.0601", major_2="None 00.0000",
                program_start=date(c - 4, 8, 20), program_end=date(c - 1, 12, 15),
                earliest_admission=date(c - 4, 7, 21), start_of_classes=date(c - 4, 8, 20),
                admission_number="555444333B2")
    mast = dict(BUSINESS, sevis_id="N0099001122", surname="TEST", given_name="AMARA", country="NIGERIA",
                level="MASTER'S", major_1="Finance 52.0801", major_2="None 00.0000",
                program_start=date(c, 8, 20), program_end=date(c + 2, 5, 15),
                earliest_admission=date(c, 7, 21), start_of_classes=date(c, 8, 20), admission_number="")
    return {
        "name": "Amara", "country": "NIGERIA",
        "i20s": [
            dict(bach, reason="INITIAL ATTENDANCE", issue_date=date(c - 4, 4, 10), employment=None,
                 travel=[date(c - 3, 12, 2)]),
            dict(bach, reason="CONTINUED ATTENDANCE", issue_date=date(c - 1, 11, 1),
                 employment=("POST-COMPLETION OPT", "FULL TIME", date(c, 2, 1), date(c + 1, 1, 31)),
                 employer=None, travel=[date(c - 1, 11, 5)]),
            # no travel signature yet on the new I-20: the Overview should say so
            dict(mast, reason="CHANGE OF EDUCATION LEVEL", issue_date=date(c, 5, 1), employment=None, travel=[]),
        ],
    }


STUDENTS = {"manuel": manuel, "priya": priya, "amara": amara}
