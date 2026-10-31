import io
from datetime import date

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from PIL import Image

from . import dates, signing
from .extract import read_image, read_pdf, render_first_page
from .signatures import saved_signature, store_signature
from .models import Document, Version
from .records import ALL_DEFS, EXTRA_NAMES, FIELD_DEFS, I20, EMPLOYER_TYPES, backfill_work, WORK_COLUMNS, WORK_TYPES, cross_checks, effective, work_checks
from vault import secure
from vault.models import Profile


def _show(value: str, kind: str) -> str:
    """Short dates for display (10 Mar 2026). Stored values stay YYYY-MM-DD."""
    if kind == "date":
        d = dates.parse(value)
        return dates.short(d) if d else value
    if kind == "dates":
        ds = dates.parse_list(value)
        return ", ".join(dates.short(d) for d in ds) if ds else value
    return value


def _sniff(data: bytes) -> str | None:
    """Decide the file type from its contents, never from its name."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    try:
        fmt = Image.open(io.BytesIO(data)).format
    except Exception:
        return None
    return {"JPEG": "image/jpeg", "PNG": "image/png"}.get(fmt)


@require_POST
def upload(request):
    f = request.FILES.get("file")
    if not f:
        return redirect("/?msg=too_large" if request.META.get("CONTENT_LENGTH", "0") != "0" else "/?msg=no_file")
    data = f.read()
    if len(data) > settings.STASH_MAX_UPLOAD_BYTES:
        return redirect("/?msg=too_large")
    mime = _sniff(data)
    if not mime:
        return redirect("/?msg=unsupported")

    existing = Version.objects.filter(fingerprint=secure.fingerprint(data)).select_related("document").first()
    if existing:
        doc = existing.document
        target = f"/documents/{doc.id}/" if doc.status == "saved" else f"/documents/{doc.id}/review"
        return redirect(target + "?dup=1")

    doc = Document.create_next("I20")
    Version.store(doc, data, mime, "upload")
    result = read_pdf(data) if mime == "application/pdf" else read_image()
    doc.set_data({
        "fields": result["fields"],
        "checks": result["checks"],
        "anchors": result.get("anchors", {}),
        "work": result.get("work", {"value": "", "confidence": "missing", "reason": "", "auths": []}),
        "source": {"text_layer": result.get("text_layer"), "scan": result.get("scan"), "mime": mime},
    })
    doc.save()
    return redirect(f"/documents/{doc.id}/review")


def _work_from_post(post, old: dict) -> dict:
    """Employment authorizations from the review form. With No, every employment field is dropped."""
    value = post.get("work_auth")
    if value not in ("yes", "no"):
        return old
    auths = []
    if value == "yes":
        cols = {key: post.getlist(f"work_{key}") for key, _, _ in WORK_COLUMNS}
        for i in range(len(cols["type"])):
            row = {}
            for key, _, kind in WORK_COLUMNS:
                raw = (cols[key][i] if i < len(cols[key]) else "").strip()[:120]
                if kind == "date":
                    raw = dates.parse(raw).isoformat() if dates.parse(raw) else ""
                row[key] = raw
            if row["type"] not in WORK_TYPES:
                continue  # the blank row, or a row with no type
            if row["employer_type"] not in EMPLOYER_TYPES:
                row["employer_type"] = ""
            auths = [row]  # one authorization per I-20
            break
        if not auths:
            value = "no"
    changed = value != old.get("value") or auths != old.get("auths", [])
    return {"value": value, "auths": auths,
            "confidence": "edited" if changed else old.get("confidence", "read"),
            "reason": "" if changed else old.get("reason", "")}


def review(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id, doc_type="I20")
    if doc.status == "saved":
        backfill_work(doc)
    data = doc.get_data()
    fields = data.setdefault("fields", {})

    if request.method == "POST":
        if request.POST.get("action") == "cancel":
            if doc.status == "draft":
                doc.remove()
                return redirect("/?msg=cancelled")
            return redirect(f"/documents/{doc.id}/")
        for name, _, _ in ALL_DEFS:
            if name not in request.POST:
                continue  # not on this form; keep what was read
            old = fields.get(name, {"value": "", "confidence": "missing", "reason": ""})
            value = request.POST.get(name, "").strip()[:200]
            entry = dict(old)
            if value != old.get("value", ""):
                entry["confidence"] = "edited"
            entry["value"] = value
            entry["doc_wrong"] = request.POST.get(f"{name}__wrong") == "on"
            entry["corrected"] = request.POST.get(f"{name}__corrected", "").strip()[:200] if entry["doc_wrong"] else ""
            entry["note"] = request.POST.get(f"{name}__note", "").strip()[:300] if entry["doc_wrong"] else ""
            fields[name] = entry
        if "work_auth" in request.POST:
            data["work"] = _work_from_post(request.POST, data.get("work", {}))
        was_draft = doc.status == "draft"
        doc.set_data(data)
        doc.status = "saved"
        doc.save()
        country = effective(fields.get("country_of_citizenship", {}))
        if country:
            profile = Profile.load()
            if profile.get("country") != country:
                profile["country"] = country  # the greeting follows it unless you chose your own
                Profile.save_data(profile)
        return redirect(f"/documents/{doc.id}/?saved={'new' if was_draft else 'edit'}")

    rows = []
    for name, label, kind in ALL_DEFS:
        fld = fields.get(name, {"value": "", "confidence": "blank" if name in EXTRA_NAMES else "missing", "reason": ""})
        rows.append({"name": name, "label": label, "kind": kind, "extra": name in EXTRA_NAMES, **fld})
    values = {name: effective(fields.get(name, {})) for name, _, _ in ALL_DEFS}
    work = data.get("work", {"value": "", "confidence": "missing", "reason": "", "auths": []})
    version = doc.versions.order_by("number").first()
    return render(request, "documents/review.html", {
        "doc": doc, "rows": rows, "checks": data.get("checks", {}),
        "warnings": cross_checks(values) + work_checks(values, work),
        "work": work, "auth": (work.get("auths") or [{}])[0],  # one authorization per I-20
        "work_types": WORK_TYPES, "employer_types": EMPLOYER_TYPES,
        "file_url": f"/documents/{doc.id}/file/{version.number}", "mime": version.mime,
        "dup": request.GET.get("dup"), "nav": "documents",
    })


def detail(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id)
    if doc.status == "draft":
        return redirect(f"/documents/{doc.id}/review")
    versions = list(doc.versions.order_by("number"))
    try:
        n = int(request.GET.get("v", versions[-1].number))
    except ValueError:
        n = versions[-1].number
    current = next((v for v in versions if v.number == n), versions[-1])
    ctx = {"doc": doc, "versions": versions, "current": current, "nav": "documents",
           "prev": current.number - 1 if current.number > 1 else None,
           "next": current.number + 1 if current.number < versions[-1].number else None,
           "dup": request.GET.get("dup"), "signed": request.GET.get("signed"), "saved": request.GET.get("saved")}
    if doc.doc_type == "I20":
        backfill_work(doc)
        rec = I20(doc)
        data = rec.data
        ctx.update({
            "rows": [{"label": label, "name": name,
                      "printed": _show(data["fields"].get(name, {}).get("value", ""), kind),
                      "value": _show(rec.values[name], kind), "wrong": name in rec.wrong,
                      "note": data["fields"].get(name, {}).get("note", "")}
                     for name, label, kind in ALL_DEFS
                     if name not in EXTRA_NAMES or rec.values.get(name) or name in rec.wrong],
            "checks": data.get("checks", {}), "warnings": cross_checks(rec.values) + work_checks(rec.values, rec.work),
            "work": [{**a, **{k: dates.short(dates.parse(a.get(k))) if a.get(k) else ""
                                for k, _, kind in WORK_COLUMNS if kind == "date"}}
                     for a in rec.work_auths_raw],
            "work_known": rec.work.get("value") in ("yes", "no"),
            "can_sign": versions[0].mime == "application/pdf",
            "sign_state": ("in_app" if data.get("checks", {}).get("student_signature", {}).get("signed_in_app")
                           else "on_document" if data.get("checks", {}).get("student_signature", {}).get("status") == "found"
                           else "needed"),
            "digital_dso": data.get("anchors", {}).get("digital_dso_signature"),
        })
    return render(request, "documents/detail.html", ctx)


def file(request, doc_id, number):
    doc = get_object_or_404(Document, id=doc_id)
    v = get_object_or_404(Version, document=doc, number=number)
    resp = HttpResponse(v.read(), content_type=v.mime)
    ext = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}.get(v.mime, "bin")
    resp["Content-Disposition"] = f'inline; filename="{doc.display_id}-v{v.number}.{ext}"'
    return resp


def sign(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id, doc_type="I20", status="saved")
    original = doc.versions.order_by("number").first()
    if original.mime != "application/pdf":
        raise Http404()
    data = doc.get_data()
    saved = saved_signature()
    pdf = original.read()
    page = render_first_page(pdf)
    width, height = (page["width"], page["height"]) if page else (612.0, 792.0)
    anchor = data.get("anchors", {}).get("student_signature")
    default = signing.default_placement(anchor, width, height)
    error = None
    if request.method == "POST":
        try:
            on = dates.parse(request.POST.get("date")) or date.today()
            if request.POST.get("source") == "saved" and saved:
                png = saved.latest_version().read()
            else:
                png = signing.clean_drawn(request.POST.get("signature", ""))
                if not saved or request.POST.get("replace_saved"):
                    saved = store_signature(png)
            place = signing.parse_placement(request.POST, default)
            Version.store(doc, signing.stamp(pdf, png, place, on), "application/pdf", "signed")
            data.setdefault("checks", {})["student_signature"] = {
                "status": "found", "detail": f"Signed in STASH, dated {dates.short(on)}", "signed_in_app": True}
            doc.set_data(data)
            doc.save()
            return redirect(f"/documents/{doc.id}/?signed=1")
        except ValueError as exc:
            error = str(exc)
    return render(request, "documents/sign.html", {
        "doc": doc, "saved": saved, "error": error, "nav": "documents", "page": page,
        "page_w": width, "page_h": height, "place": default,
        "pct": {k: round(v * 100, 2) for k, v in default.items()},
        "located": bool(anchor), "today": date.today().isoformat(),
        "digital_dso": data.get("anchors", {}).get("digital_dso_signature"),
    })


def signature_image(request):
    saved = saved_signature()
    if not saved:
        raise Http404()
    return HttpResponse(saved.latest_version().read(), content_type="image/png")


@require_POST
def delete(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id)
    doc.remove()
    return redirect("/documents/?msg=deleted")


def index(request):
    """Documents tab: one section per document type, each with its own columns."""
    from dashboard.views import _doc_rows  # noqa: avoid a cycle at import time
    from .records import saved_i20s, work_color
    records = saved_i20s()
    i20s = []
    for row in _doc_rows(records):
        r = row["record"]
        auth = r.work_auths[0] if r.work_auths else None
        i20s.append({**row, "level": r.level, "school": r.school, "versions": r.doc.versions.count(),
                     "flags": r.flags, "employment": row["label"] if row["label"] != "Program" else "",
                     "color": work_color(auth)[0] if auth else ""})
    signed_on = [d.display_id for d in Document.objects.filter(doc_type="I20", status="saved", versions__kind="signed").distinct()]
    sigs = []
    for n, d in enumerate(Document.objects.filter(doc_type="SIG", status="saved").order_by("-seq")):
        latest = d.latest_version()
        sigs.append({"doc": d, "versions": d.versions.count(), "updated": dates.short(latest.created_at.astimezone().date()) if latest else "—",
                     "used_on": ", ".join(signed_on) or "—", "status": "Current" if n == 0 else "Superseded"})
    return render(request, "documents/index.html", {
        "i20s": i20s, "sigs": sigs, "nav": "documents", "msg": request.GET.get("msg"),
        "has_any": bool(i20s or sigs),
    })
