from datetime import date


def parse(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def plus_one_year(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + 1, day=28)


def short(d: date | None) -> str:
    return f"{d.day} {d.strftime('%b %Y')}" if d else "—"


def parse_list(value) -> list[date]:
    out = []
    for part in str(value or "").replace(";", ",").split(","):
        d = parse(part)
        if d and d not in out:
            out.append(d)
    return sorted(out)
