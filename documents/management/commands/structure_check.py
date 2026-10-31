"""Prints the layout of a PDF with every value masked, so you can check what STASH
sees in a real I-20 without the file or its contents going anywhere.

    python manage.py structure_check ~/Downloads/my-i20.pdf
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from documents import pdfread


class Command(BaseCommand):
    help = "Show a PDF's labels and layout with all values masked (x for letters, 9 for digits)."

    def add_arguments(self, parser):
        parser.add_argument("pdf")

    def handle(self, *args, **opts):
        path = Path(opts["pdf"]).expanduser()
        if not path.is_file():
            raise CommandError(f"No file at {path}")
        data = path.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise CommandError("That file isn't a PDF.")
        self.stdout.write(pdfread.structure(data))
        found = pdfread.extract(data)
        self.stdout.write("\n--- what STASH would extract (values masked) ---")
        for name, f in found["fields"].items():
            masked = "".join("9" if c.isdigit() else "x" if c.isalpha() else c for c in f["value"])
            self.stdout.write(f"  {name:<18} {f['confidence']:<8} {masked or '-'}  {f.get('reason', '')}")
        for name, c in found["checks"].items():
            self.stdout.write(f"  check {name:<18} {c['status']}")
