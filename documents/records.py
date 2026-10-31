"""Reads saved I-20s back as plain values for the screens."""
import re
from datetime import date

from . import dates
from .models import Document

FIELD_DEFS = [
    ("sevis_id", "SEVIS ID", "text"),
    ("issue_date", "Issue date", "date"),
    ("issue_reason", "Issue reason", "text"),
    ("education_level", "Education level", "text"),
    ("program_start", "Program start", "date"),
    ("program_end", "Program end", "date"),
    ("school", "School", "text"),
    ("travel_signatures", "Travel signature dates", "dates"),
    ("country_of_citizenship", "Country of citizenship", "text"),  # only used for the greeting
]
# Page-1 details for the Overview cards. Often blank on real I-20s, which is fine.
EXTRA_DEFS = [
    ("admission_number", "Admission number", "text"),
    ("earliest_admission", "Earliest admission date", "date"),
    ("start_of_classes", "Start of classes", "date"),
    ("school_code", "School code", "text"),
    ("school_approval", "School approval date", "date"),
    ("school_official", "School official (DSO)", "text"),
    ("school_official_title", "School official's title", "text"),
    ("major_1", "Major 1", "text"),
    ("major_1_cip", "Major 1 CIP code", "text"),
    ("major_2", "Major 2", "text"),
    ("major_2_cip", "Major 2 CIP code", "text"),
]
ALL_DEFS = FIELD_DEFS + EXTRA_DEFS
EXTRA_NAMES = {name for name, _, _ in EXTRA_DEFS}

WORK_TYPES = ["CPT", "OPT", "STEM OPT"]
# Employment columns from the inventory sheet. One employer per authorization.
WORK_COLUMNS = [
    ("type", "Employment type", "choice"),
    ("start", "Employment start", "date"),
    ("end", "Employment end", "date"),
    ("employer_type", "Employer type", "choice"),
    ("employer_name", "Employer name", "text"),
    ("employer_start", "Employer start", "date"),
    ("employer_end", "Employer end", "date"),
    ("city", "City", "text"),
    ("state", "State", "text"),
]
EMPLOYER_TYPES = ["CPT", "OPT", "STEM OPT"]  # as printed on the I-20
# CPT takes a lighter shade of the degree it falls within; OPT jade, STEM OPT emerald.
CPT_COLORS = {"bachelor": "#A3B8D8", "master": "#C9A3C4", "doctor": "#BCC594", "other": "#A9BFD9"}
WORK_COLORS = {"OPT": ("#2A9D8F", "#D4EEEA"), "STEM OPT": ("#2D7D5A", "#D3EBDD")}
GRACE_COLOR = "#C93A32"

LEVEL_COLORS = {"bachelor": "#2C5282", "master": "#7E4A78", "doctor": "#4E5D1E", "other": "#3B6EA8"}
LEVEL_NAMES = {"bachelor": "Bachelor's", "master": "Master's", "doctor": "PhD", "other": "Other program"}


def effective(field: dict) -> str:
    """What's true: the correction if the document itself is wrong, else what's printed."""
    if field.get("doc_wrong") and field.get("corrected"):
        return field["corrected"]
    return field.get("value", "")


def level_key(text: str) -> str:
    t = (text or "").upper()
    if "BACHELOR" in t:
        return "bachelor"
    if "MASTER" in t:
        return "master"
    if "DOCTOR" in t or "PHD" in t or "PH.D" in t:
        return "doctor"
    return "other"


def cross_checks(values: dict) -> list[str]:
    """Warnings only. Nothing here blocks saving."""
    out = []
    sevis = values.get("sevis_id", "")
    if sevis and not re.fullmatch(r"N\d{10}", sevis):
        out.append("SEVIS ID should be N followed by 10 digits.")
    issued = dates.parse(values.get("issue_date"))
    start, end = dates.parse(values.get("program_start")), dates.parse(values.get("program_end"))
    if issued and issued > date.today():
        out.append("Issue date is in the future.")
    if start and end and end <= start:
        out.append("Program end is not after program start.")
    for d in dates.parse_list(values.get("travel_signatures")):
        if issued and d < issued:
            out.append(f"Travel signature {dates.short(d)} is before the issue date.")
    return out


def work_checks(values: dict, work: dict) -> list[str]:
    """Warnings for the employment section. Nothing here blocks saving."""
    out = []
    p_start, p_end = dates.parse(values.get("program_start")), dates.parse(values.get("program_end"))
    for a in work.get("auths", []) if work.get("value") == "yes" else []:
        s, e = dates.parse(a.get("start")), dates.parse(a.get("end"))
        name = a.get("type", "Work authorization")
        if not (s and e):
            out.append(f"{name} is missing a start or end date.")
            continue
        if e <= s:
            out.append(f"{name} end date is not after its start date.")
        if name == "CPT" and p_start and p_end and (s < p_start or e > p_end):
            out.append("CPT falls outside the program dates.")
        if name == "OPT" and (e - s).days > 366:
            out.append("OPT runs longer than 12 months.")
        if name == "STEM OPT" and (e - s).days > 731:
            out.append("STEM OPT runs longer than 24 months.")
        es, ee = dates.parse(a.get("employer_start")), dates.parse(a.get("employer_end"))
        if es and ee and ee < es:
            out.append(f"{a.get('employer_name') or 'Employer'} end date is before its start date.")
    return out


class I20:
    def __init__(self, doc: Document):
        self.doc = doc
        self.data = doc.get_data()
        fields = self.data.get("fields", {})
        self.values = {name: effective(fields.get(name, {})) for name, _, _ in ALL_DEFS}
        self.wrong = [name for name, _, _ in ALL_DEFS if fields.get(name, {}).get("doc_wrong")]

    def __getattr__(self, name):
        raise AttributeError(name)

    @property
    def display_id(self):
        return self.doc.display_id

    @property
    def issue_date(self):
        return dates.parse(self.values["issue_date"])

    @property
    def program_start(self):
        return dates.parse(self.values["program_start"])

    @property
    def program_end(self):
        return dates.parse(self.values["program_end"])

    @property
    def travel_dates(self):
        return dates.parse_list(self.values["travel_signatures"])

    @property
    def school(self):
        return self.values["school"]

    @property
    def reason(self):
        return self.values["issue_reason"]

    @property
    def level(self):
        return self.values["education_level"]

    @property
    def level_key(self):
        return level_key(self.level)

    @property
    def work(self) -> dict:
        return self.data.get("work", {})

    @property
    def work_auths_raw(self) -> list[dict]:
        return list(self.work.get("auths", [])) if self.work.get("value") == "yes" else []

    @property
    def work_auths(self) -> list[dict]:
        """Authorizations with real dates, for the dashboard."""
        out = []
        for a in self.work_auths_raw:
            s, e = dates.parse(a.get("start")), dates.parse(a.get("end"))
            if a.get("type") in WORK_TYPES and s and e:
                out.append({**a, "start": s, "end": e, "record": self})
        return out

    @property
    def flags(self):
        return len(self.wrong) + len(cross_checks(self.values)) + len(work_checks(self.values, self.work))


def all_work(records) -> list[dict]:
    """Every authorization across your I-20s, once each (reissued I-20s repeat them)."""
    seen, out = set(), []
    for r in sorted(records, key=lambda r: (r.issue_date or date.min), reverse=True):
        for a in r.work_auths:
            key = (a["type"], a["start"])
            if key not in seen:  # the newest I-20 wins if dates changed
                seen.add(key)
                out.append(a)
    return sorted(out, key=lambda a: a["start"])


def next_program_start(a, records):
    """Start of the next program after the one this authorization belongs to, if any.
    Changing education level normally ends CPT, OPT and STEM OPT from the earlier program."""
    own = a["record"].program_start
    later = [r.program_start for r in records if r.program_start and own and r.program_start > own]
    return min(later) if later else None


def counting_work(records, on):
    """Authorizations that still count on a given day: drop those whose program was followed
    by a new program that had started by then. They stay in your history."""
    out = []
    for a in all_work(records):
        nxt = next_program_start(a, records)
        if nxt and nxt <= on:
            continue
        out.append(a)
    return out


def work_color(a) -> tuple[str, str]:
    if a["type"] == "CPT":
        c = CPT_COLORS[a["record"].level_key]
        return c, c + "55"
    return WORK_COLORS[a["type"]]


def backfill_work(doc: Document) -> None:
    """I-20s saved before a field existed (employment, page-1 details): read the missing parts
    from the original upload once, and mark them for you to check. Fields you saved aren't touched."""
    data = doc.get_data()
    fields = data.setdefault("fields", {})
    missing_extra = [n for n in EXTRA_NAMES if n not in fields]
    if "work" in data and not missing_extra:
        return
    from .extract import read_pdf
    original = doc.versions.order_by("number").first()
    result = read_pdf(original.read()) if original and original.mime == "application/pdf" else {}
    note = "Added later from your original upload. Check it against the document"
    if "work" not in data:
        work = result.get("work") or {"value": "", "confidence": "missing",
                                       "reason": "Enter from the employment section", "auths": []}
        if work.get("value"):
            work = dict(work, confidence="check", reason=note)
        data["work"] = work
    for n in missing_extra:
        got = result.get("fields", {}).get(n) or {"value": "", "confidence": "blank", "reason": "Not printed on this I-20"}
        fields[n] = dict(got, confidence="check", reason=note) if got.get("value") else got
    doc.set_data(data)
    doc.save(update_fields=["data_enc"])


def saved_i20s() -> list[I20]:
    docs = list(Document.objects.filter(doc_type="I20", status="saved"))
    for d in docs:
        backfill_work(d)
    items = [I20(d) for d in docs]
    return sorted(items, key=lambda r: (r.issue_date or date.min, r.doc.seq))
