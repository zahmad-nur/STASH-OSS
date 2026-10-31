"""Signatures: cleaning a drawn or uploaded signature, and placing it on an I-20.
Runs locally with Pillow, pypdf and reportlab; nothing is sent anywhere."""
import base64
import io
from datetime import date

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

MAX_SIGNATURE_BYTES = 5 * 1024 * 1024
SIG_ASPECT = 3.5          # the placement box is 3.5x wider than tall
DATE_FONT = 9


def _trim_and_encode(img: Image.Image) -> bytes:
    if img.width > 2400 or img.height > 1200:
        img.thumbnail((2400, 1200))
    bbox = img.getchannel("A").getbbox()  # trim empty space around the strokes
    if not bbox:
        raise ValueError("The signature is empty.")
    out = io.BytesIO()
    img.crop(bbox).save(out, format="PNG")  # re-encoding drops any metadata in the original
    return out.getvalue()


def clean_drawn(data_url: str) -> bytes:
    """A signature drawn in the browser (transparent PNG data URL)."""
    if not data_url.startswith("data:image/png;base64,"):
        raise ValueError("Draw your signature first.")
    raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise ValueError("Signature image is too large.")
    img = Image.open(io.BytesIO(raw))
    img.verify()
    return _trim_and_encode(Image.open(io.BytesIO(raw)).convert("RGBA"))


def clean_uploaded(raw: bytes) -> bytes:
    """A PNG or JPG of a signature. Light paper becomes transparent, so the
    signature doesn't cover the lines on the form."""
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise ValueError("Signature image is over 5 MB.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    except Exception:
        raise ValueError("That file isn't a readable PNG or JPG.")
    if img.format not in ("PNG", "JPEG", "MPO") and img.format is not None:
        raise ValueError("Use a PNG or JPG.")
    rgba = img.convert("RGBA")
    gray = ImageOps.grayscale(rgba)
    # ink stays, paper goes: darker pixels keep opacity in proportion to how dark they are
    alpha = gray.point(lambda v: 0 if v > 200 else min(255, int((200 - v) * 2.2)))
    alpha = Image.composite(alpha, Image.new("L", alpha.size, 0), rgba.getchannel("A"))
    ink = Image.new("RGBA", rgba.size, (20, 22, 26, 255))
    ink.putalpha(alpha)
    return _trim_and_encode(ink)


def default_placement(anchor: dict | None, width: float, height: float) -> dict:
    """Starting positions as fractions of the page (top-left origin)."""
    sig_w = 120.0 / width
    sig_h_pts = sig_w * width / SIG_ASPECT
    if anchor:
        place = {"sig_x": (anchor["x1"] + 8) / width, "sig_y": (anchor["bottom"] + 3 - sig_h_pts) / height, "sig_w": sig_w}
        d = anchor.get("date")
        if d:
            place.update(date_x=(d["x1"] + 6) / width, date_y=(d["bottom"] - DATE_FONT - 2) / height)
        else:
            place.update(date_x=place["sig_x"] + sig_w + 0.03, date_y=place["sig_y"])
    else:
        place = {"sig_x": 0.1, "sig_y": 0.82, "sig_w": sig_w, "date_x": 0.6, "date_y": 0.84}
    return {k: round(min(max(v, 0.0), 0.98), 4) for k, v in place.items()}


def stamp(pdf_bytes: bytes, png: bytes, place: dict, on: date, page_index: int = 0) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted:
        reader.decrypt("")
    page = reader.pages[page_index]
    width, height = float(page.mediabox.width), float(page.mediabox.height)

    box_x, box_top = place["sig_x"] * width, place["sig_y"] * height
    box_w = place["sig_w"] * width
    box_h = box_w / SIG_ASPECT
    img = ImageReader(io.BytesIO(png))
    iw, ih = img.getSize()
    if box_w / box_h > iw / ih:
        draw_h, draw_w = box_h, box_h * iw / ih
    else:
        draw_w, draw_h = box_w, box_w * ih / iw

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    # reportlab measures from the bottom of the page; the signature sits on the box's bottom edge
    c.drawImage(img, box_x, height - box_top - box_h, width=draw_w, height=draw_h, mask="auto")
    c.setFont("Helvetica", DATE_FONT)
    c.drawString(place["date_x"] * width, height - place["date_y"] * height - DATE_FONT, on.strftime("%m/%d/%Y"))
    c.save()

    overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
    writer = PdfWriter()
    for i, p in enumerate(reader.pages):
        if i == page_index:
            p.merge_page(overlay)
        writer.add_page(p)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def parse_placement(post, fallback: dict) -> dict:
    place = {}
    for key in ("sig_x", "sig_y", "sig_w", "date_x", "date_y"):
        try:
            v = float(post.get(key, ""))
        except ValueError:
            v = fallback[key]
        place[key] = min(max(v, 0.0), 0.98)
    place["sig_w"] = min(max(place["sig_w"], 0.08), 0.6)
    return place
