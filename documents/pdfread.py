"""Reads an I-20 PDF. Runs in a separate, isolated Python process (see extract.py),
so a malformed file can't hang or crash the app, and it never touches the database
or the network. It imports only the standard library, pdfplumber and pypdf.

Run as a worker:   python -I pdfread.py --worker   (PDF bytes on stdin, JSON on stdout)
"""
import io
import json
import re
import sys

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
MONTH_RE = r"(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUNE?|JULY?|AUG(?:UST)?|SEPT?(?:EMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)"
DATE_RES = [
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[\s-]+" + MONTH_RE + r"\.?[\s-]+(\d{4})\b", re.I), "d_mon_y"),
    (re.compile(r"\b" + MONTH_RE + r"\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.I), "mon_d_y"),
]

# The eight-field map. Labels are matched case-insensitively.
FIELD_LABELS = {
    "issue_date": ["DATE ISSUED"],
    "issue_reason": ["FORM ISSUE REASON", "ISSUE REASON"],
    "education_level": ["EDUCATION LEVEL"],
    "program_dates": ["PROGRAM START/END DATE", "PROGRAM START / END DATE", "PROGRAM START/END"],
    "school": ["SCHOOL NAME"],
    "country_of_citizenship": ["COUNTRY OF CITIZENSHIP"],  # used only for the greeting
    # page-1 details shown on the Overview cards
    "admission_number": ["ADMISSION NUMBER"],
    "earliest_admission": ["EARLIEST ADMISSION DATE"],
    "start_of_classes": ["START OF CLASSES"],
    "school_code": ["SCHOOL CODE AND APPROVAL DATE"],
    "school_official": ["SCHOOL OFFICIAL TO CONTACT UPON ARRIVAL"],
    "major_1": ["MAJOR 1"],
    "major_2": ["MAJOR 2"],
}
# Fields that are often left blank on real I-20s. Blank is normal for these, not an error.
EXTRA_FIELDS = ["admission_number", "earliest_admission", "start_of_classes", "school_code", "school_approval",
                "school_official", "school_official_title", "major_1", "major_1_cip", "major_2", "major_2_cip"]
CIP_RE = re.compile(r"\b(\d{2}\.\d{4})\b")
# Other labels printed on the I-20. Used to find column edges and for the masked structure check.
OTHER_LABELS = [
    "SEVIS ID", "SURNAME/PRIMARY NAME", "GIVEN NAME", "PREFERRED NAME", "PASSPORT NAME",
    "COUNTRY OF BIRTH", "DATE OF BIRTH",
    "CITY OF BIRTH", "LEGACY NAME", "CLASS OF ADMISSION", "SCHOOL ADDRESS",
    "PROGRAM ENGLISH PROFICIENCY",
    "ENGLISH PROFICIENCY NOTES", "PLACE ISSUED",
    "SCHOOL ATTESTATION", "STUDENT ATTESTATION", "SIGNATURE OF", "TRAVEL ENDORSEMENT",
    "EMPLOYMENT AUTHORIZATIONS", "REMARKS", "FINANCIALS", "DATE",
]
ALL_LABELS = [p for ps in FIELD_LABELS.values() for p in ps] + OTHER_LABELS
# Words in the employment section that describe the form, not you. Left unmasked in the structure check.
WORK_WORDS = {"TYPE", "FULL", "PART", "TIME", "FULL/PART", "START", "END", "STATUS", "APPROVED", "REQUESTED",
              "EMPLOYER", "NAME", "ADDRESS", "CPT", "OPT", "STEM", "CURRICULAR", "OPTIONAL", "PRACTICAL",
              "TRAINING", "POST-COMPLETION", "PRE-COMPLETION", "EXTENSION", "24-MONTH", "-", "/"}
VOCAB = {t for p in ALL_LABELS for t in p.split()} | WORK_WORDS
# Headings that end the employment section.
SECTION_ENDS = ("TRAVEL ENDORSEMENT", "REMARKS", "SCHOOL ATTESTATION", "STUDENT ATTESTATION", "FINANCIALS",
                "INSTRUCTIONS TO STUDENTS")


# ---------- dates ----------

def _iso(y, m, d):
    try:
        y, m, d = int(y), int(m), int(d)
    except ValueError:
        return None
    if 1 <= m <= 12 and 1 <= d <= 31 and 1900 < y < 2200:
        return f"{y:04d}-{m:02d}-{d:02d}"
    return None


def find_dates(text: str) -> list[str]:
    found = []
    for rx, kind in DATE_RES:
        for m in rx.finditer(text):
            g = m.groups()
            if kind == "mdy":
                iso = _iso(g[2], g[0], g[1])
            elif kind == "ymd":
                iso = _iso(g[0], g[1], g[2])
            elif kind == "d_mon_y":
                iso = _iso(g[2], MONTHS[g[1][:3].upper()], g[0])
            else:
                iso = _iso(g[2], MONTHS[g[0][:3].upper()], g[1])
            if iso:
                found.append((m.start(), iso))
    found.sort()
    out = []
    for _, iso in found:
        if iso not in out:
            out.append(iso)
    return out


# ---------- employment authorizations ----------

def work_type(line: str) -> str:
    """CPT, OPT or STEM OPT from a line of the employment section ('' if none)."""
    t = line.upper()
    if re.search(r"\bSTEM\b|24[- ]MONTH", t):
        return "STEM OPT"
    if re.search(r"\bCPT\b|CURRICULAR", t):
        return "CPT"
    if re.search(r"\bOPT\b|OPTIONAL PRACTICAL|POST-COMPLETION|PRE-COMPLETION", t):
        return "OPT"
    return ""


CITY_STATE = re.compile(r"([A-Za-z][A-Za-z .'-]+),\s*([A-Z]{2})\b(?:\s+\d{5})?")


def _after(label: str, lines: list[str]) -> str:
    """The text after a label on its line, or the next line if the label stands alone."""
    for i, ln in enumerate(lines):
        u = ln.upper()
        if label in u:
            rest = ln[u.index(label) + len(label):].strip(" :")
            if rest:
                return rest
            return lines[i + 1].strip() if i + 1 < len(lines) else ""
    return ""


def read_work(pages_text: list[str]) -> dict:
    """Employment authorizations listed after page 1. Each starts at a line naming its type.
    The first two dates in that block are the authorization's start and end; any further two
    belong to the employer. Employer details are marked for checking."""
    for text in pages_text:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        head = next((i for i, ln in enumerate(lines) if "EMPLOYMENT AUTHORIZATION" in ln.upper()), None)
        if head is None:
            continue
        section = []
        for ln in lines[head + 1:]:
            if any(ln.upper().startswith(e) for e in SECTION_ENDS):
                break
            section.append(ln)
        # a new authorization starts at a line naming its type (an "Employer type" line doesn't count)
        starts = [i for i, ln in enumerate(section) if work_type(ln) and not ln.upper().startswith("EMPLOYER")]
        auths = []
        for n, i in enumerate(starts):
            stop = starts[n + 1] if n + 1 < len(starts) else len(section)
            block = section[i:min(stop, i + 8)]
            found = find_dates(" ".join(block))
            address = _after("EMPLOYER ADDRESS", block)
            place = CITY_STATE.search(address) if address else None
            auths.append({
                "type": work_type(section[i]),
                "start": found[0] if found else "", "end": found[1] if len(found) > 1 else "",
                "employer_type": work_type(_after("EMPLOYER TYPE", block)),  # only as printed on the I-20
                "employer_name": _after("EMPLOYER NAME", block),
                "employer_start": found[2] if len(found) > 2 else "",
                "employer_end": found[3] if len(found) > 3 else "",
                "city": place.group(1).strip() if place else "",
                "state": place.group(2) if place else "",
            })
        if auths:
            # An I-20 carries one authorization at a time; keep the latest if more are printed.
            auths = [max(auths, key=lambda a: a["start"] or "")]
            ok = all(a["start"] and a["end"] for a in auths)
            return {"value": "yes", "confidence": "read" if ok else "check",
                    "reason": "Check the employer details against the document" if ok
                    else "Some dates weren't found. Fill them in from the document",
                    "auths": auths}
        return {"value": "no", "confidence": "read", "reason": "Employment section lists none", "auths": []}
    return {"value": "no", "confidence": "check", "reason": "No employment section found. Check page 2", "auths": []}


# ---------- layout helpers ----------

def _norm(text: str) -> str:
    return text.upper().strip().rstrip(":")


def _find_phrase(words, phrase):
    tokens = phrase.split()
    hits = []
    for i in range(len(words) - len(tokens) + 1):
        group = words[i:i + len(tokens)]
        if all(_norm(w["text"]) == t for w, t in zip(group, tokens)) and \
                all(abs(w["top"] - group[0]["top"]) < 3 for w in group):
            hits.append({
                "x0": min(w["x0"] for w in group), "x1": max(w["x1"] for w in group),
                "top": min(w["top"] for w in group), "bottom": max(w["bottom"] for w in group),
                "ids": [id(w) for w in group], "phrase": phrase,
            })
    return hits


def _part_of_value(words, h) -> bool:
    """A label phrase printed inside a value, e.g. EDUCATION LEVEL in the issue reason
    "CHANGE OF EDUCATION LEVEL": another word runs right up to it on the same line."""
    return any(abs(w["top"] - h["top"]) < 3 and h["x0"] - 8 < w["x1"] <= h["x0"] + 0.5 and id(w) not in h["ids"]
               for w in words)


def _all_hits(words):
    hits = []
    for phrase in sorted(ALL_LABELS, key=lambda p: -len(p.split())):
        for h in _find_phrase(words, phrase):
            # skip a shorter label inside a longer one already found (e.g. DATE in DATE ISSUED)
            if any(set(h["ids"]) & set(o["ids"]) for o in hits) or _part_of_value(words, h):
                continue
            hits.append(h)
    return hits


def _value_near(words, label, hits, label_ids):
    """The value printed under a label (I-20 style), or else to its right."""
    same_line_starts = [h["x0"] for h in hits if abs(h["top"] - label["top"]) < 3 and h["x0"] > label["x0"] + 5]
    right_edge = min(same_line_starts + [label["x0"] + 260])
    below = [w for w in words if id(w) not in label_ids
             and label["bottom"] - 1 < w["top"] < label["bottom"] + 28
             and label["x0"] - 4 <= w["x0"] < right_edge]
    if not below:
        below = [w for w in words if id(w) not in label_ids
                 and abs(w["top"] - label["top"]) < 3 and label["x1"] < w["x0"] < min(right_edge, label["x1"] + 250)]
    if not below:
        return ""
    first_top = min(w["top"] for w in below)
    line = sorted((w for w in below if abs(w["top"] - first_top) < 3), key=lambda w: w["x0"])
    return " ".join(w["text"] for w in line).strip()


def _value_lines(words, label, hits, label_ids, n=2):
    """Up to n lines printed under a label, within its column."""
    same_line_starts = [h["x0"] for h in hits if abs(h["top"] - label["top"]) < 3 and h["x0"] > label["x0"] + 5]
    right_edge = min(same_line_starts + [label["x0"] + 260])
    below = [w for w in words if id(w) not in label_ids
             and label["bottom"] - 1 < w["top"] < label["bottom"] + 14 * n + 14
             and label["x0"] - 4 <= w["x0"] < right_edge]
    lines = {}
    for w in below:
        key = next((k for k in lines if abs(k - w["top"]) < 3), w["top"])
        lines.setdefault(key, []).append(w)
    out = [" ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"])) for _, ws in sorted(lines.items())]
    return out[:n]


def _major(raw: str):
    """'Computer Science 11.0701' -> ('Computer Science', '11.0701'). 'None 00.0000' counts as blank."""
    m = CIP_RE.search(raw or "")
    cip = m.group(1) if m else ""
    name = CIP_RE.sub("", raw or "").strip(" -,:")
    if cip == "00.0000" or name.upper() in ("NONE", "N/A", ""):
        return ("", "") if cip in ("", "00.0000") else (name, cip)
    return name, cip


def _objects_in(page, box):
    """Images and drawn curves inside a box. Printed text and ruled lines don't count."""
    x0, top, x1, bottom = box
    n = 0
    for obj in list(page.images) + list(page.curves):
        if obj["x1"] > x0 and obj["x0"] < x1 and obj["bottom"] > top and obj["top"] < bottom:
            n += 1
    return n


def _is_scan(page) -> bool:
    area = float(page.width) * float(page.height)
    return any((im["x1"] - im["x0"]) * (im["bottom"] - im["top"]) > 0.8 * area for im in page.images)


def _field(value, confidence, reason=""):
    return {"value": value, "confidence": confidence, "reason": reason}


# ---------- extraction ----------

def extract(data: bytes) -> dict:
    import pdfplumber
    from pypdf import PdfReader

    result = {"text_layer": False, "scan": False, "pages": 0, "fields": {}, "checks": {}, "anchors": {},
              "work": {"value": "", "confidence": "missing", "reason": "", "auths": []}}
    digital_sig = False
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        for f in (reader.get_fields() or {}).values():
            if f.get("/FT") == "/Sig" and f.get("/V"):
                digital_sig = True
    except Exception:
        pass

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        result["pages"] = len(pdf.pages)
        p1 = pdf.pages[0]
        result["page1_size"] = [float(p1.width), float(p1.height)]
        result["text_layer"] = len(p1.chars) > 50
        result["scan"] = _is_scan(p1)
        if not result["text_layer"]:
            reason = "Scanned image, no readable text" if result["scan"] else "No readable text"
            for name in ["sevis_id", "issue_date", "issue_reason", "education_level",
                         "program_start", "program_end", "school", "travel_signatures",
                         "country_of_citizenship"] + EXTRA_FIELDS:
                result["fields"][name] = _field("", "missing", reason)
            result["work"]["reason"] = "Enter from the employment section on page 2"
            unknown = {"status": "unknown", "detail": "Can't tell from a scanned image. Check by eye."}
            result["checks"] = {"dso_signature": unknown, "student_signature": unknown,
                                "issue_date": {"status": "unknown", "detail": "Enter it from the document."}}
            return result

        words = p1.extract_words(x_tolerance=1.5, y_tolerance=2)
        hits = _all_hits(words)
        label_ids = {i for h in hits for i in h["ids"]}
        f = result["fields"]

        text1 = p1.extract_text() or ""
        m = re.search(r"\bN\d{10}\b", text1)
        f["sevis_id"] = _field(m.group(0), "read") if m else _field("", "missing", "Not found on page 1")

        def labelled(key):
            for phrase in FIELD_LABELS[key]:
                for h in hits:
                    if h["phrase"] == phrase:
                        return h, _value_near(words, h, hits, label_ids)
            return None, ""

        _, raw = labelled("issue_date")
        dates = find_dates(raw)
        f["issue_date"] = _field(dates[0], "read") if dates else _field("", "missing", "Date issued not found")

        for key in ("issue_reason", "education_level", "school", "country_of_citizenship"):
            _, raw = labelled(key)
            f[key] = _field(raw, "read") if raw else _field("", "missing", "Label not found")

        # page-1 details: blank is normal on many I-20s
        def extra(key, value):
            f[key] = _field(value, "read") if value else _field("", "blank", "Not printed on this I-20")

        _, raw = labelled("admission_number")
        extra("admission_number", raw if re.search(r"\d{6,}", raw or "") else "")
        for key in ("earliest_admission", "start_of_classes"):
            _, raw = labelled(key)
            d = find_dates(raw)
            extra(key, d[0] if d else "")
        _, raw = labelled("school_code")
        code = re.search(r"\b[A-Z]{3}\d{3}[A-Z]\d{5,8}\b", raw or "")
        d = find_dates(raw)
        extra("school_code", code.group(0) if code else "")
        extra("school_approval", d[0] if d else "")
        h, _ = labelled("school_official")
        lines = _value_lines(words, h, hits, label_ids) if h else []
        extra("school_official", lines[0] if lines else "")
        extra("school_official_title", lines[1] if len(lines) > 1 and len(lines[1]) < 60 else "")
        for n in ("1", "2"):
            _, raw = labelled(f"major_{n}")
            name, cip = _major(raw)
            extra(f"major_{n}", name)
            extra(f"major_{n}_cip", cip)

        _, raw = labelled("program_dates")
        dates = find_dates(raw)
        if len(dates) >= 2:
            f["program_start"], f["program_end"] = _field(dates[0], "read"), _field(dates[1], "read")
        else:
            f["program_start"] = _field(dates[0] if dates else "", "check" if dates else "missing", "Program dates unclear")
            f["program_end"] = _field("", "missing", "Program dates unclear")

        # travel signatures: page 2, below the travel endorsement heading; usually handwritten
        travel = []
        if len(pdf.pages) > 1:
            p2 = pdf.pages[1]
            w2 = p2.extract_words(x_tolerance=1.5, y_tolerance=2)
            heads = _find_phrase(w2, "TRAVEL ENDORSEMENT")
            if heads:
                below = [w for w in w2 if w["top"] > heads[0]["top"]]
                lines = {}
                for w in below:
                    lines.setdefault(round(w["top"]), []).append(w["text"])
                for _, ws in sorted(lines.items()):
                    travel += [d for d in find_dates(" ".join(ws)) if d not in travel]
        f["travel_signatures"] = _field(", ".join(travel), "check",
                                        "Typed dates found. Check against handwriting" if travel
                                        else "Often handwritten. Enter from page 2")

        result["work"] = read_work([p.extract_text() or "" for p in pdf.pages[1:]])

        # signature checks
        sigs = sorted([h for h in hits if h["phrase"] == "SIGNATURE OF"], key=lambda h: h["top"])
        student_head = next((h for h in hits if h["phrase"] == "STUDENT ATTESTATION"), None)
        if student_head:
            dso_label = next((h for h in reversed(sigs) if h["top"] < student_head["top"]), None)
            student_label = next((h for h in sigs if h["top"] > student_head["top"]), None)
        else:
            dso_label = sigs[0] if sigs else None
            student_label = sigs[1] if len(sigs) > 1 else None

        def box_of(label):
            return (label["x1"], label["top"] - 28, label["x1"] + 260, label["bottom"] + 10)

        if digital_sig:
            result["checks"]["dso_signature"] = {"status": "found", "detail": "Digital signature in the PDF"}
        elif dso_label and _objects_in(p1, box_of(dso_label)):
            result["checks"]["dso_signature"] = {"status": "found", "detail": "Signature mark on the DSO line"}
        elif dso_label:
            result["checks"]["dso_signature"] = {"status": "not_detected", "detail": "Nothing drawn on the DSO line"}
        else:
            result["checks"]["dso_signature"] = {"status": "unknown", "detail": "DSO signature line not located"}

        if student_label and _objects_in(p1, box_of(student_label)):
            result["checks"]["student_signature"] = {"status": "found", "detail": "Signature mark on the student line"}
        elif student_label:
            result["checks"]["student_signature"] = {"status": "not_detected", "detail": "Not signed yet"}
        else:
            result["checks"]["student_signature"] = {"status": "unknown", "detail": "Student signature line not located"}

        result["checks"]["issue_date"] = (
            {"status": "found", "detail": "On the document"} if f["issue_date"]["value"]
            else {"status": "not_detected", "detail": "No issue date found"})

        if student_label:
            date_label = next((h for h in hits if h["phrase"] == "DATE" and abs(h["top"] - student_label["top"]) < 8
                               and h["x0"] > student_label["x1"]), None)
            result["anchors"]["student_signature"] = {
                "page": 0, "x1": student_label["x1"], "top": student_label["top"],
                "bottom": student_label["bottom"],
                "date": {"x1": date_label["x1"], "bottom": date_label["bottom"]} if date_label else None,
            }
        result["anchors"]["digital_dso_signature"] = digital_sig
    return result


# ---------- masked structure report (for checking a real I-20 without sharing it) ----------

def structure(data: bytes) -> str:
    import pdfplumber

    def mask(token):
        if _norm(token) in VOCAB and not any(ch.isdigit() for ch in token):
            return token
        return re.sub(r"[0-9]", "9", re.sub(r"[A-Za-z]", "x", token))

    out = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        out.append(f"pages: {len(pdf.pages)}")
        for n, page in enumerate(pdf.pages, start=1):
            out.append(f"\n--- page {n}: {len(page.chars)} text characters, {len(page.images)} images, "
                       f"{len(page.curves)} drawn curves, scanned={_is_scan(page)}")
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
            for h in sorted(_all_hits(words), key=lambda h: (h["top"], h["x0"])):
                out.append(f"  label  {h['phrase']:<40} x={h['x0']:6.1f} y={h['top']:6.1f}")
            out.append("  text (masked):")
            for line in (page.extract_text() or "").splitlines():
                out.append("    " + " ".join(mask(t) for t in line.split()))
    return "\n".join(out)


def render_page(data: bytes, index: int = 0, scale: float = 1.6) -> dict:
    """Draws one page as a PNG so you can place your signature on it."""
    import base64
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    page = pdf[index]
    width, height = page.get_size()
    img = page.render(scale=scale).to_pil()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"width": width, "height": height, "png": base64.b64encode(buf.getvalue()).decode()}


if __name__ == "__main__" and "--render" in sys.argv:
    try:
        sys.stdout.write(json.dumps(render_page(sys.stdin.buffer.read())))
    except Exception as exc:
        sys.stdout.write(json.dumps({"error": type(exc).__name__}))

if __name__ == "__main__" and "--worker" in sys.argv:
    try:
        import resource
        limit = 2 * 1024 ** 3
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except Exception:
        pass
    payload = sys.stdin.buffer.read()
    try:
        sys.stdout.write(json.dumps(extract(payload)))
    except Exception as exc:  # report the kind of failure, never document contents
        sys.stdout.write(json.dumps({"error": type(exc).__name__}))
