"""
Download Philadelphia parking violations from the city's Carto SQL API
and save them to a single CSV.

Usage:
    python philly_parking_violations.py                      # 2018-01-01 to today
    python philly_parking_violations.py --start 2017-01-01 --out pv_2017.csv

The data is pulled one month at a time so no single request gets too big.
"""

import argparse
import csv
import io
import sys
import time
from datetime import date

import requests

API_URL = "https://phl.carto.com/api/v2/sql"
TABLE = "parking_violations"
# Carto adds these geometry/ID columns; we already get lat and lon as plain columns.
SKIP_FIELDS = "cartodb_id,the_geom,the_geom_webmercator"


def month_starts(start, end):
    """Yield the first day of each month from start's month up to and including end's month."""
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def next_month(d):
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def fetch_csv(sql, retries=5):
    """Run a SQL query against Carto and return the result as CSV text.

    Carto sometimes returns a 400/429/5xx on large queries (timeouts, rate limits)
    that succeed if you try again, so retry with an increasing wait.
    """
    params = {"q": sql, "format": "csv", "skipfields": SKIP_FIELDS}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=300)
            if resp.ok:
                return resp.text
            problem = f"HTTP {resp.status_code}: {resp.text[:300]}"
        except requests.RequestException as e:
            problem = str(e)
        if attempt == retries:
            raise RuntimeError(f"Giving up after {retries} tries. Last error: {problem}\nQuery: {sql}")
        wait = 10 * attempt
        print(f"  request failed ({problem.strip()}); retrying in {wait}s...", file=sys.stderr)
        time.sleep(wait)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2018-01-01", help="first date to include (YYYY-MM-DD)")
    parser.add_argument("--end", default=date.today().isoformat(), help="last date to include (YYYY-MM-DD)")
    parser.add_argument("--out", default="philly_parking_violations.csv", help="output CSV path")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    # Tell the user up front what date range the table actually covers.
    info = requests.get(
        API_URL,
        params={"q": f"SELECT min(issue_datetime), max(issue_datetime) FROM {TABLE}"},
        timeout=120,
    ).json()["rows"][0]
    print(f"Table covers {info['min'][:10]} to {info['max'][:10]}")

    total = 0
    header_written = False
    with open(args.out, "w", newline="", encoding="utf-8") as outfile:
        writer = csv.writer(outfile)
        for month in month_starts(start, end):
            lo = max(month, start)
            hi = min(next_month(month), date.fromordinal(end.toordinal() + 1))
            sql = (
                f"SELECT * FROM {TABLE} "
                f"WHERE issue_datetime >= '{lo}' AND issue_datetime < '{hi}' "
                f"ORDER BY issue_datetime, anon_ticket_number"
            )
            rows = list(csv.reader(io.StringIO(fetch_csv(sql))))
            if not rows:
                continue
            header, data = rows[0], rows[1:]
            if not header_written:
                writer.writerow(header)
                header_written = True
            writer.writerows(data)
            total += len(data)
            print(f"{month:%Y-%m}: {len(data):,} rows")

    if total == 0:
        print(f"No records found between {start} and {end}.", file=sys.stderr)
    else:
        print(f"Saved {total:,} rows to {args.out}")


if __name__ == "__main__":
    main()
