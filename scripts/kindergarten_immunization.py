#!/usr/bin/env python3
"""Download Maryland kindergarten immunization spreadsheets and combine them
into long-format CSVs with a school_year column.

Two CSVs are written because the measures differ:

  * 2015-2016 through 2022-2023 are COMPLIANCE rates (share of students
    meeting school requirements) -> data/md_kindergarten_immunization_compliance.csv
  * 2023-2024 onward are COVERAGE rates -> data/md_kindergarten_immunization_coverage.csv

Source page:
https://health.maryland.gov/phpa/OIDEOR/IMMUN/pages/kindergarten_immunization_rates_by_school.aspx

Each school year is published as a separate .xlsx (older years are hosted on
marylandvfc.org). Column headers and number formats drift between years, so
this script normalizes them:

  * headers are mapped to stable snake_case names
  * rates are expressed as percentages (0-100) in every year; years that
    stored fractions (0-1) are multiplied by 100
  * impossible rates (below 0 or above 100) are blanked and logged
  * redacted cells ("**", "<10" for schools with fewer than 10 kindergartners)
    are left blank and flagged in a `redacted` column
  * school_type is normalized to "Public" / "Private"

Usage:
    python3 scripts/kindergarten_immunization.py
    python3 scripts/kindergarten_immunization.py -o out.csv --cache-dir raw/ --force

Requires: openpyxl
"""

import argparse
import csv
import html
import logging
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import openpyxl

PAGE_URL = (
    "https://health.maryland.gov/phpa/OIDEOR/IMMUN/pages/"
    "kindergarten_immunization_rates_by_school.aspx"
)
USER_AGENT = "Mozilla/5.0 (compatible; kindergarten-immunization-scraper)"

# Output columns, in order. Percent columns are listed in PCT_COLUMNS below.
COLUMNS = [
    "school_year",
    "school_name",
    "county",
    "school_type",
    "total_k_students",
    "k_students_with_records",
    "k_students_without_records",
    "k_students_surveyed",
    "pct_medical_exemption",
    "pct_religious_exemption",
    "pct_dtap",
    "pct_polio",
    "pct_mmr",
    "pct_hep_b",
    "pct_varicella",
    "redacted",
    "source_url",
]
PCT_COLUMNS = [c for c in COLUMNS if c.startswith("pct_")]
COUNT_COLUMNS = [
    "total_k_students",
    "k_students_with_records",
    "k_students_without_records",
    "k_students_surveyed",
]
REDACTED_TOKENS = {"**", "<10"}
# School years before this are compliance rates; this year and later are coverage.
COVERAGE_START = "2023-2024"

log = logging.getLogger("kindergarten_immunization")


def norm_header(text):
    """Lowercase a header and collapse whitespace/punctuation for matching."""
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def map_header(text):
    """Map a raw spreadsheet header to one of COLUMNS (or None if unknown)."""
    h = norm_header(text)
    if not h:
        return None
    if h.startswith("school name"):
        return "school_name"
    if h == "county":
        return "county"
    if h.startswith("type of school"):
        return "school_type"
    if "without" in h:
        return "k_students_without_records"
    if "with records" in h:
        return "k_students_with_records"
    if "surveyed" in h:
        return "k_students_surveyed"
    if h.startswith("total"):
        return "total_k_students"
    if h.startswith("%"):
        key = h.lstrip("% ").replace(" ", "_")
        pct = {
            "medical_exemption": "pct_medical_exemption",
            "religious_exemption": "pct_religious_exemption",
            "dtap": "pct_dtap",
            "polio": "pct_polio",
            "mmr": "pct_mmr",
            "hep_b": "pct_hep_b",
            "varicella": "pct_varicella",
        }.get(key)
        if pct:
            return pct
    log.warning("Unrecognized header %r", text)
    return None


def find_spreadsheet_links(page_html, base_url=PAGE_URL):
    """Return [(school_year, absolute_url), ...] for every linked .xls/.xlsx."""
    links = []
    seen = set()
    for href in re.findall(r'href="([^"]+?\.xlsx?)"', page_html, flags=re.I):
        href = html.unescape(href)
        url = urllib.parse.urljoin(base_url, href)
        # Encode spaces etc. but leave already-encoded %20 alone.
        url = urllib.parse.quote(url, safe=":/%?=&")
        m = re.search(r"(\d{4})\s*-\s*(\d{4})", urllib.parse.unquote(href))
        if not m:
            log.warning("Skipping link without a school year: %s", url)
            continue
        year = f"{m.group(1)}-{m.group(2)}"
        if year in seen:
            log.warning("Duplicate link for %s, keeping first: %s", year, url)
            continue
        seen.add(year)
        links.append((year, url))
    return sorted(links)


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def download(url, dest, force=False):
    if dest.exists() and not force:
        log.info("Using cached %s", dest.name)
        return dest
    log.info("Downloading %s", url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(fetch(url))
    return dest


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def norm_school_type(value):
    t = clean_text(value).lower()
    if t.startswith("public"):
        return "Public"
    if t.startswith("private") or "non-public" in t:
        return "Private"
    return clean_text(value)


def parse_number(value):
    """Return (number_or_None, is_redacted)."""
    if value is None:
        return None, False
    if isinstance(value, (int, float)):
        return value, False
    s = str(value).strip()
    if s in REDACTED_TOKENS:
        return None, True
    if s == "":
        return None, False
    try:
        return float(s.replace("%", "").replace(",", "")), False
    except ValueError:
        log.warning("Non-numeric value %r treated as missing", value)
        return None, False


def parse_workbook(path, school_year, source_url):
    """Parse one year's workbook into a list of row dicts."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            header_idx = next(
                (i for i, r in enumerate(rows)
                 if r and norm_header(r[0]).startswith("school name")),
                None,
            )
            if header_idx is not None:
                break
        else:
            raise ValueError(f"{path.name}: no sheet with a 'School Name' header")
    finally:
        wb.close()

    header = rows[header_idx]
    col_map = {i: map_header(h) for i, h in enumerate(header) if h is not None}
    col_map = {i: c for i, c in col_map.items() if c}
    missing = {"school_name", "county"} - set(col_map.values())
    if missing:
        raise ValueError(f"{path.name}: missing required columns {missing}")

    records = []
    for raw in rows[header_idx + 1:]:
        if raw is None or all(v is None or str(v).strip() == "" for v in raw):
            continue
        rec = {c: None for c in COLUMNS}
        rec["school_year"] = school_year
        rec["source_url"] = source_url
        rec["redacted"] = False
        for idx, col in col_map.items():
            val = raw[idx] if idx < len(raw) else None
            if col == "school_name":
                rec[col] = clean_text(val)
            elif col == "county":
                rec[col] = clean_text(val)
            elif col == "school_type":
                rec[col] = norm_school_type(val)
            else:
                num, red = parse_number(val)
                rec[col] = num
                rec["redacted"] = rec["redacted"] or red
        if not rec["school_name"]:
            continue
        records.append(rec)

    # Some years store rates as fractions (0-1), later years as percents
    # (0-100). Decide per file using the median, since a stray bad cell
    # (e.g. 9.08 in a fractions file) must not flip the whole year.
    pct_values = sorted(
        r[c] for r in records for c in PCT_COLUMNS if isinstance(r[c], (int, float))
    )
    median = pct_values[len(pct_values) // 2] if pct_values else 100
    scale = 100.0 if median <= 1.0 else 1.0
    log.info(
        "%s: %d schools, rates stored as %s",
        school_year, len(records), "fractions" if scale == 100.0 else "percent",
    )
    bad = 0
    for r in records:
        for c in PCT_COLUMNS:
            if isinstance(r[c], (int, float)):
                v = round(r[c] * scale, 2)
                if v < 0 or v > 100:
                    log.warning(
                        "%s: %s / %s: %s = %s is out of range, blanked",
                        school_year, r["school_name"], r["county"], c, v,
                    )
                    v = None
                    bad += 1
                r[c] = v
        for c in COUNT_COLUMNS:
            if isinstance(r[c], float) and r[c].is_integer():
                r[c] = int(r[c])
    if bad:
        log.warning("%s: blanked %d out-of-range rate cells", school_year, bad)
    return records


def write_csv(rows, out):
    """Write rows to out, dropping columns that are empty for every row."""
    cols = [
        c for c in COLUMNS
        if c in ("school_year", "school_name", "county", "source_url")
        or any(r[c] not in (None, "") for r in rows)
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r[c] is None else r[c]) for c in cols})
    log.info("Wrote %d rows to %s", len(rows), out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "-o", "--output",
        default="data/md_kindergarten_immunization_coverage.csv",
        help=f"coverage-rate CSV, {COVERAGE_START} onward (default: %(default)s)",
    )
    ap.add_argument(
        "--compliance-output",
        default="data/md_kindergarten_immunization_compliance.csv",
        help=f"compliance-rate CSV, years before {COVERAGE_START} (default: %(default)s)",
    )
    ap.add_argument(
        "--cache-dir",
        default="data/raw/kindergarten_immunization",
        help="where to keep the downloaded .xlsx files (default: %(default)s)",
    )
    ap.add_argument("--force", action="store_true", help="re-download cached files")
    ap.add_argument("--page-url", default=PAGE_URL, help=argparse.SUPPRESS)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    log.info("Fetching index page %s", args.page_url)
    page = fetch(args.page_url).decode("utf-8", errors="replace")
    links = find_spreadsheet_links(page, args.page_url)
    if not links:
        log.error("No spreadsheet links found on the page")
        return 1
    log.info("Found %d spreadsheets: %s", len(links), ", ".join(y for y, _ in links))

    cache = Path(args.cache_dir)
    all_rows = []
    failures = []
    for year, url in links:
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".xlsx"
        dest = cache / f"{year}{ext}"
        try:
            download(url, dest, force=args.force)
            all_rows.extend(parse_workbook(dest, year, url))
        except Exception as exc:  # keep going; report at the end
            log.error("%s: %s", year, exc)
            failures.append(year)

    all_rows.sort(key=lambda r: (r["school_year"], r["county"], r["school_name"]))

    coverage = [r for r in all_rows if r["school_year"] >= COVERAGE_START]
    compliance = [r for r in all_rows if r["school_year"] < COVERAGE_START]
    write_csv(coverage, Path(args.output))
    write_csv(compliance, Path(args.compliance_output))

    if failures:
        log.error("Failed years: %s", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
