"""
Download and parse the monthly South Philadelphia Sports Complex event
calendars published by the Sports Complex Special Services District
(https://scssd.org/sports-complex-info/) into a single CSV.

Each PDF is a one-page calendar grid. We find the grid by locating the
day-of-month numbers (we know which weekday column each date belongs in),
then split each day's cell into events at lines like "7:00 PM – WFC".

Usage:
    uv run python data/scssd_events.py [--start-year 2018] [--out data/scssd_events.csv]
"""

import argparse
import calendar
import csv
import re
import time
from datetime import date
from pathlib import Path

import pdfplumber
import requests

PAGE_URL = "https://scssd.org/sports-complex-info/"
HEADERS = {"User-Agent": "Mozilla/5.0 (jour405 class project)"}

# "7:00 PM – WFC", "12:00 PM - Refinery", "TBD – LFF", "9:00 AM – 8PM – WFC",
# "4:30 PM to 10 PM – FDR Park", "9:00 AM – 3PM"
_T = r"\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?|TBD(?:\s*[AP]M)?|TBA|Noon"
TIME_RE = re.compile(
    rf"^\*?\s*(?P<time>{_T})"
    rf"(?:\s*(?:to|[–—-])\s*(?P<end>\d{{1,2}}(?::\d{{2}})?\s*[AP]\.?M\.?))?"
    r"(?:\s*[–—-]+\s*(?P<venue>.*))?$",
    re.I,
)
ATTENDANCE_RE = re.compile(r"\((?P<att>[\d,]+|n/a)\)", re.I)


def get_pdf_list(start_year):
    """Return [(year, month, url)] from the JSON embedded in the page."""
    html = requests.get(PAGE_URL, headers=HEADERS, timeout=60).text
    pattern = re.compile(
        r'\{"month":"(\d\d)\\/(\d{4})","pdf_file":\{.*?"url":"([^"]+)"', re.S
    )
    seen = {}
    for m, y, url in pattern.findall(html):
        y, m = int(y), int(m)
        if y >= start_year:
            seen[(y, m)] = url.replace("\\/", "/")
    return [(y, m, u) for (y, m), u in sorted(seen.items())]


def download(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise ValueError(f"not a PDF: {url}")
    dest.write_bytes(r.content)
    time.sleep(0.5)
    return dest


def make_words(chars, x_tol=1.5, y_tol=2.5):
    """Build words from characters. pdfplumber's extract_words can interleave
    characters from adjacent lines in some of these PDFs, so do it by hand:
    cluster characters into lines by position, then split on gaps."""
    lines = []
    for c in sorted(chars, key=lambda c: (c["top"], c["x0"])):
        if lines and abs(lines[-1][0]["top"] - c["top"]) <= y_tol:
            lines[-1].append(c)
        else:
            lines.append([c])
    words = []
    for line in lines:
        word = None
        for c in sorted(line, key=lambda c: c["x0"]):
            if c["text"].isspace():
                word = None
                continue
            if word and c["x0"] - word["x1"] <= x_tol:
                word["text"] += c["text"]
                word["x1"] = c["x1"]
            else:
                word = {"text": c["text"], "x0": c["x0"], "x1": c["x1"],
                        "top": line[0]["top"], "bottom": c["bottom"]}
                words.append(word)
    return words


def group_lines(words, tol=2.5):
    """Group words into text lines by vertical position."""
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1]["top"] - w["top"]) <= tol:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    out = []
    for line in lines:
        text = " ".join(w["text"] for w in sorted(line["words"], key=lambda w: w["x0"]))
        # pdfplumber often glues the dash to the venue ("–WFC")
        text = re.sub(r"\s*([–—])\s*", r" \1 ", text)
        out.append(re.sub(r"\s+", " ", text).strip())
    return out


def find_date_tokens(words, year, month):
    """Locate the word holding each day number; return {day: word}."""
    ndays = calendar.monthrange(year, month)[1]
    first_col = (calendar.weekday(year, month, 1) + 1) % 7  # Sunday = 0
    # header (SUN ... SAT) gives rough column centers
    header = {}
    for w in words:
        t = w["text"].upper()
        for i, name in enumerate(["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]):
            if t.startswith(name) and i not in header:
                header[i] = w
    if len(header) < 6:
        raise ValueError("could not find weekday header")
    header_bottom = max(w["bottom"] for w in header.values())
    centers = {i: (w["x0"] + w["x1"]) / 2 for i, w in header.items()}
    # some PDFs are missing a weekday label; columns are evenly spaced
    known = sorted(centers)
    step = (centers[known[-1]] - centers[known[0]]) / (known[-1] - known[0])
    centers = [centers.get(i, centers[known[0]] + (i - known[0]) * step) for i in range(7)]
    bounds = [0] + [(centers[i] + centers[i + 1]) / 2 for i in range(6)] + [1e9]

    def col_of(w):
        for i in range(7):
            if bounds[i] - 8 <= w["x0"] < bounds[i + 1] - 8:
                return i
        return 6

    found = {}
    last_top = header_bottom - 1
    for day in range(1, ndays + 1):
        col = (first_col + day - 1) % 7
        pat = re.compile(rf"^{day}(?!\d)(?!:)")
        cands = [
            w
            for w in words
            if w["top"] > last_top - 3
            and col_of(w) == col
            and pat.match(w["text"])
        ]
        if col == 0 or day == 1:
            # new week row: must be below the previous row
            cands = [w for w in cands if w["top"] > last_top + 5 or day == 1]
        if not cands:
            raise ValueError(f"could not find day {day}")
        tok = min(cands, key=lambda w: (w["top"], w["x0"]))
        found[day] = tok
        last_top = tok["top"]
    return found


def parse_pdf(path, year, month):
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        words = make_words(page.chars)

    dates = find_date_tokens(words, year, month)
    first_col = (calendar.weekday(year, month, 1) + 1) % 7

    # column left edges come from the date numbers themselves
    col_x = {}
    for day, w in dates.items():
        col = (first_col + day - 1) % 7
        col_x[col] = min(col_x.get(col, 1e9), w["x0"])
    edges = [col_x.get(i) for i in range(7)]
    edges = [e - 3 for e in edges] + [page.width]

    # week rows start at each date row's top; grid ends at the footer legend
    footer_top = min(
        [w["top"] for w in words if re.match(r"(Neighborhood|www\.scssd|Venues)", w["text"])]
        + [page.height]
    )
    row_tops = sorted({round(w["top"]) for w in dates.values()})

    def row_bottom(top):
        later = [t for t in row_tops if t > top + 3]
        return later[0] - 1 if later else footer_top - 1

    rows = []
    for day, tok in dates.items():
        col = (first_col + day - 1) % 7
        x0, x1 = edges[col], edges[col + 1]
        y0, y1 = tok["top"] - 1, row_bottom(tok["top"])
        cell = [
            w for w in words
            if x0 <= w["x0"] < x1 and y0 <= w["top"] < y1
        ]
        # drop the date line (day number plus any holiday label)
        cell = [w for w in cell if abs(w["top"] - tok["top"]) > 6]
        for ev in split_events(group_lines(cell)):
            rows.append({
                "year": year,
                "month": month,
                "date": date(year, month, day).isoformat(),
                **ev,
            })
    return rows


def split_events(lines):
    events = []
    current = None
    banner = None
    for line in lines:
        m = TIME_RE.match(line)
        if m and (m.group("end") or m.group("venue") is not None):
            current = {
                "time": m.group("time"),
                "end_time": m.group("end"),
                "venue": (m.group("venue") or "").strip(),
                "banner": banner,
                "lines": [],
            }
            banner = None
            events.append(current)
        elif re.match(r"^\\+.*/+$", line):
            # "\\\ Community Event ///" banner: a label for the next event
            banner = line.strip("\\/ ")
        else:
            if current is None:
                current = {"time": None, "end_time": None, "venue": None, "banner": None, "lines": []}
                events.append(current)
            current["lines"].append(line)

    out = []
    for ev in events:
        text_lines, notes = [], []
        for line in ev["lines"]:
            if line.startswith(">"):
                notes.append(line.lstrip("> ").strip())
            elif notes and text_lines and not ATTENDANCE_RE.fullmatch(line):
                # wrapped continuation of a ">>>" note that follows the event name
                notes[-1] += " " + line
            else:
                text_lines.append(line)
        text = " ".join(text_lines)
        att = ATTENDANCE_RE.search(text)
        attendance = None
        if att and att.group("att").lower() != "n/a":
            attendance = int(att.group("att").replace(",", ""))
        text = ATTENDANCE_RE.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not ev["time"]:
            if not text:
                continue
            # a lone untimed line (New Year's Eve, Tax Day) is a holiday label
            if len(text_lines) == 1 and not notes and attendance is None:
                continue
        out.append({
            "time": normalize_time(ev["time"]),
            "end_time": normalize_time(ev["end_time"]),
            "venue": ev["venue"] or None,
            "event": text or None,
            "attendance": attendance,
            "notes": "; ".join(([ev["banner"]] if ev["banner"] else []) + notes) or None,
        })
    return out


def normalize_time(t):
    """'7:00 PM' -> '19:00'; TBD/TBA -> None."""
    if t is None or t.upper().startswith(("TBD", "TBA")):
        return None
    if t.lower() == "noon":
        return "12:00"
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*([AP])", t, re.I)
    h, mins, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).upper()
    if ap == "P" and h != 12:
        h += 12
    if ap == "A" and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--pdf-dir", default="data/scssd_pdfs")
    parser.add_argument("--out", default="data/scssd_events.csv")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    fields = ["month", "month_name", "year", "date", "time", "end_time", "venue", "event", "attendance", "notes", "source"]
    all_rows = []
    for year, month, url in get_pdf_list(args.start_year):
        dest = pdf_dir / f"{year}-{month:02d}_{url.rsplit('/', 1)[-1]}"
        try:
            download(url, dest)
            rows = parse_pdf(dest, year, month)
        except Exception as e:
            print(f"{year}-{month:02d}: FAILED ({e})")
            continue
        for r in rows:
            r["month_name"] = calendar.month_name[month]
            r["source"] = url
        print(f"{year}-{month:02d}: {len(rows)} events")
        all_rows.extend(rows)

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"wrote {len(all_rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
