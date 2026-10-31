from datetime import date

from django.shortcuts import redirect, render

from documents import dates
from documents.records import (GRACE_COLOR, LEVEL_COLORS, LEVEL_NAMES, all_work, counting_work, next_program_start,
                              saved_i20s, work_color)

MESSAGES = {
    "too_large": "That file is over 20 MB.",
    "unsupported": "STASH accepts PDFs, JPEGs and PNGs.",
    "no_file": "Choose a file to upload.",
    "cancelled": "Upload cancelled. The file and everything read from it were deleted.",
}


def _program_end_card(current):
    if not current or not current.program_end:
        return None
    days = (current.program_end - date.today()).days
    return {"date": dates.short(current.program_end),
            "note": f"{days} days left" if days >= 0 else f"Ended {-days} days ago"}


def _active_work(work, on):
    return next((a for a in reversed(work) if a["start"] <= on <= a["end"]), None)


def _phase(current, work=()):
    if not current or not (current.program_start and current.program_end):
        return None
    today = date.today()
    active = _active_work(list(work), today)
    if active and active["type"] != "CPT":
        employer = f" with {active['employer_name']}" if active.get("employer_name") else ""
        return {"title": f"On {active['type']}", "enrolled": False, "work": True,
                "line": f"{active['type']}{employer} runs until {dates.short(active['end'])}."}
    level = LEVEL_NAMES.get(current.level_key, "Program")
    if today < current.program_start:
        return {"title": "Before your program starts", "enrolled": False,
                "line": f"{level} at {current.school} starts {dates.short(current.program_start)}."}
    if today <= current.program_end:
        return {"title": "Enrolled", "enrolled": True,
                "line": f"{level} at {current.school} runs until {dates.short(current.program_end)}."}
    return {"title": "Program ended", "enrolled": False,
            "line": f"{level} at {current.school} ended {dates.short(current.program_end)}."}


def _travel(records, current):
    """Latest signature on the current I-20 only. A signature applies to the I-20 it's on,
    so an older I-20's signature never counts for the current one."""
    if not current:
        return None
    if not current.travel_dates:
        return {"missing": True, "expired": True, "sort": date.max}
    source = current
    signed_on = source.travel_dates[-1]
    expires = dates.plus_one_year(signed_on)
    total = (expires - signed_on).days
    used = min(max((date.today() - signed_on).days, 0), total)
    left = (expires - date.today()).days
    return {"signed": dates.short(signed_on), "expires": dates.short(expires), "pct": round(100 * used / total),
            "tag": f"In {left} days" if left >= 0 else f"Expired {-left} days ago", "expired": left < 0,
            "source": source.display_id, "on_current": source is current, "sort": expires}


def _work_card(work):
    """The authorization in effect today, or else the most recent one."""
    if not work:
        return None
    today = date.today()
    a = _active_work(work, today) or max(work, key=lambda a: a["end"])
    total = max((a["end"] - a["start"]).days, 1)
    used = min(max((today - a["start"]).days, 0), total)
    left = (a["end"] - today).days
    color, tint = work_color(a)
    return {"type": a["type"], "ends": dates.short(a["end"]), "start": dates.short(a["start"]),
            "pct": round(100 * used / total), "color": color, "tint": tint, "expired": left < 0,
            "tag": f"In {left} days" if left >= 0 else f"Ended {-left} days ago",
            "employer": a.get("employer_name", ""), "source": a["record"].display_id, "sort": a["end"]}


STUDY_TINT = ("#F8E4E2", "#6E1F1A", "#A3302A")  # Field of Study card: a soft red, as School Contact is a soft green


def _doc_rows(records):
    """Overview table. The same columns for every document type; each type fills them its own way."""
    rows = []
    for n, r in enumerate(reversed(records)):
        auth = r.work_auths[0] if r.work_auths else None
        raw = r.work_auths_raw[0] if r.work_auths_raw else None
        if auth:
            start, end = auth["start"], auth["end"]
        else:
            start, end = r.program_start, r.program_end
        rows.append({"record": r, "type": "I-20", "issued": dates.short(r.issue_date),
                     "description": (r.reason or "").capitalize() or "—",
                     "dates": f"{dates.short(start)} – {dates.short(end)}" if start or end else "—",
                     "label": raw["type"] if raw else "Program",
                     # the newest of each document type is current; older ones are superseded
                     "status": "Current" if n == 0 else "Superseded"})
    return rows


def _mask(sevis: str) -> str:
    return sevis[:3] + "••••" + sevis[-4:] if len(sevis) >= 8 else sevis


def _i20_card(current):
    """Current I-20 card: only rows that have a value on the document."""
    if not current:
        return None
    v = current.values
    rows = []
    if v.get("sevis_id"):
        rows.append({"label": "SEVIS ID", "value": _mask(v["sevis_id"]), "full": v["sevis_id"], "mono": True})
    if v.get("admission_number"):
        rows.append({"label": "Admission number", "value": v["admission_number"], "note": "Your I-94 number", "mono": True})
    if dates.parse(v.get("earliest_admission")):
        rows.append({"label": "Earliest admission", "value": dates.short(dates.parse(v["earliest_admission"])), "mono": True})
    if v.get("school_code"):
        approved = dates.parse(v.get("school_approval"))
        rows.append({"label": "School code", "value": v["school_code"], "mono": True,
                     "note": f"Approved {dates.short(approved)}" if approved else ""})
    auth = current.work_auths_raw[0] if current.work_auths_raw else None
    if auth and auth.get("employer_name"):
        place = ", ".join(p for p in (auth.get("city"), auth.get("state")) if p)
        rows.append({"label": "Employer", "value": auth["employer_name"], "note": place})
        es = dates.parse(auth.get("employer_start"))
        if es:
            rows.append({"label": "Employer start", "value": dates.short(es), "mono": True})
    elif not auth and dates.parse(v.get("start_of_classes")):
        rows.append({"label": "Start of classes", "value": dates.short(dates.parse(v["start_of_classes"])), "mono": True})
    return {"issued": dates.short(current.issue_date), "rows": rows, "doc": current.doc}


def _info_cards(current):
    if not current:
        return {}
    v = current.values
    contact = {"name": v["school_official"], "title": v.get("school_official_title", ""),
               "school": current.school} if v.get("school_official") else None
    majors = [{"name": v[f"major_{n}"], "cip": v.get(f"major_{n}_cip", ""), "n": n}
              for n in ("1", "2") if v.get(f"major_{n}")]
    bg, ink, sub = STUDY_TINT
    study = {"majors": majors, "level": LEVEL_NAMES.get(current.level_key, ""), "bg": bg, "ink": ink, "sub": sub,
             "stem_note": any(m["cip"] for m in majors)} if majors else None
    return {"contact": contact, "study": study}


def overview(request):
    records = saved_i20s()
    current = records[-1] if records else None
    travel = _travel(records, current)
    work = counting_work(records, date.today())
    cards = sorted([c for c in [dict(travel, kind="travel") if travel else None,
                                dict(_work_card(work), kind="work") if work else None] if c],
                   key=lambda c: (c["expired"], c["sort"]))
    return render(request, "dashboard/overview.html", {
        "nav": "overview", "records": list(reversed(records)), "doc_rows": _doc_rows(records),
        "i20_card": _i20_card(current), **_info_cards(current), "current": current,
        "end_card": _program_end_card(current), "phase": _phase(current, work), "travel": travel, "cards": cards,
        "msg": MESSAGES.get(request.GET.get("msg", "")),
    })


PENDING_COLOR = "#D6D3CC"  # grey: a stretch the documents don't explain yet


def _color_at(segments, left):
    """Color of the top segment under a point on the timeline (the bar's background if none)."""
    hit = [s for s in segments if s["left"] <= left <= s["left"] + s["width"]]
    return hit[-1]["color"] if hit else "#F6F5F1"


def _is_light(hex_color: str) -> bool:
    h = hex_color.lstrip("#")[:6]
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55


def stay(request):
    records = saved_i20s()
    groups = {}
    for r in records:
        if r.program_start and r.program_end:
            g = groups.setdefault(r.level_key, {"start": r.program_start, "end": r.program_end, "ids": []})
            g["start"], g["end"] = min(g["start"], r.program_start), max(g["end"], r.program_end)
            g["ids"].append(r.display_id)
    work = all_work(records)
    ctx = {"nav": "stay", "has_data": bool(groups)}
    if groups:
        today = date.today()
        # Travel signatures aren't part of your stay. Entries will come from I-94s.
        lo = min([g["start"] for g in groups.values()] + [a["start"] for a in work])
        hi = max([g["end"] for g in groups.values()] + [a["end"] for a in work] + [today])
        span = max((hi - lo).days, 1)

        def pct(d):
            return round(100 * (d - lo).days / span, 2)

        segments = []
        for key, g in sorted(groups.items(), key=lambda kv: kv[1]["start"]):
            segments.append({"left": pct(g["start"]), "width": max(pct(g["end"]) - pct(g["start"]), 0.6),
                             "color": LEVEL_COLORS[key], "name": LEVEL_NAMES[key],
                             "tip": f"{LEVEL_NAMES[key]} · {dates.short(g['start'])} – {dates.short(g['end'])}"})
        # grace period: from a program's end until the OPT that follows it starts
        ends = sorted(g["end"] for g in groups.values())
        for a in work:
            if a["type"] != "OPT":
                continue
            before = [e for e in ends if e < a["start"]]
            if before and (a["start"] - before[-1]).days > 1:
                g0 = before[-1]
                segments.append({"left": pct(g0), "width": max(pct(a["start"]) - pct(g0), 0.4), "color": GRACE_COLOR,
                                 "name": "Grace period", "tip": f"Grace period · {dates.short(g0)} – {dates.short(a['start'])}"})
        for a in work:
            color, _ = work_color(a)
            name = f"{LEVEL_NAMES[a['record'].level_key]} CPT" if a["type"] == "CPT" else a["type"]
            nxt = next_program_start(a, records)
            end = min(a["end"], nxt) if nxt else a["end"]  # ends when the next program starts
            if end <= a["start"]:
                continue
            note = f" (ended when your next program started; printed end {dates.short(a['end'])})" if end < a["end"] else ""
            segments.append({"left": pct(a["start"]), "width": max(pct(end) - pct(a["start"]), 0.6),
                             "color": color, "name": name,
                             "tip": f"{name} · {dates.short(a['start'])} – {dates.short(end)}{note}"})
        years = [{"label": y, "left": pct(date(y, 1, 1))} for y in range(lo.year + 1, hi.year + 1)]
        ctx.update({
            "segments": segments, "years": years, "today_left": pct(today),
            "markers": [],  # US entries from I-94s go here; white or charcoal via _is_light(_color_at(...))
            "legend": list({s["name"]: {"name": s["name"], "color": s["color"]} for s in segments}.values()),
            "range": f"{dates.short(lo)} – {dates.short(hi)}",
        })
    return render(request, "dashboard/stay.html", ctx)


def lookup(request):
    records = saved_i20s()
    raw = request.GET.get("date", "")
    on = dates.parse(raw)
    ctx = {"nav": "lookup", "date": raw, "has_data": bool(records)}
    if on and records:
        issued = [r for r in records if r.issue_date and r.issue_date <= on]
        doc = max(issued, key=lambda r: r.issue_date) if issued else None
        sig = None
        for r in records:
            for s in r.travel_dates:
                if s <= on <= dates.plus_one_year(s) and (not sig or s > sig["date"]):
                    sig = {"date": s, "doc": r.display_id}
        program = None
        if doc and doc.program_start and doc.program_end:
            if on < doc.program_start:
                program = "Before the program start date"
            elif on <= doc.program_end:
                program = "Inside the program dates"
            else:
                program = "After the program end date"
        active = _active_work(counting_work(records, on), on)
        ctx["result"] = {
            "work": {"type": active["type"], "start": dates.short(active["start"]), "end": dates.short(active["end"]),
                     "employer": active.get("employer_name", ""), "doc": active["record"].display_id} if active else None,
            "label": dates.short(on), "doc": doc, "program": program,
            "start": dates.short(doc.program_start) if doc else None,
            "end": dates.short(doc.program_end) if doc else None,
            "issued": dates.short(doc.issue_date) if doc else None,
            "sig": {"date": dates.short(sig["date"]), "expires": dates.short(dates.plus_one_year(sig["date"])),
                    "doc": sig["doc"]} if sig else None,
        }
    return render(request, "dashboard/lookup.html", ctx)


def settings_page(request):
    from documents import signing
    from documents.signatures import saved_signature, store_signature
    from vault import greetings
    from vault.models import Profile

    profile = Profile.load()
    error = None
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "profile":
                mode = request.POST.get("greeting_mode", "auto")
                profile.update(name=request.POST.get("name", "").strip()[:60],
                               greeting=request.POST.get("greeting", "").strip()[:60],
                               greeting_mode=mode if mode in ("auto", "custom", "off") else "auto",
                               native_script=request.POST.get("native_script") == "on")
                Profile.save_data(profile)
                return redirect("/settings?saved=profile")
            if action == "upload_sig":
                f = request.FILES.get("file")
                if not f:
                    raise ValueError("Choose an image file.")
                store_signature(signing.clean_uploaded(f.read()))
                return redirect("/settings?saved=signature")
            if action == "draw_sig":
                store_signature(signing.clean_drawn(request.POST.get("signature", "")))
                return redirect("/settings?saved=signature")
        except ValueError as exc:
            error = str(exc)
    sig = saved_signature()
    return render(request, "dashboard/settings.html", {
        "nav": "settings", "profile": profile, "error": error, "saved": request.GET.get("saved"),
        "auto_greeting": greetings.for_country(profile.get("country", ""), native=profile.get("native_script", True))
        or {"text": "Welcome", "lang": "en", "dir": "ltr", "latin": "Welcome"},
        "signature": sig, "sig_versions": sig.versions.count() if sig else 0,
        "native_script": profile.get("native_script", True),
    })
