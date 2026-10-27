"""
Download Prince George's County crash reports from the Maryland State Police
public crash dashboard (Tableau), one month at a time, and combine them into
a single CSV with a month column.

Source dashboard:
https://analytics.mdsp.org/t/Public/views/PublicCrash2/PublicCrash

The dashboard's "Crash Map" sheet has one row per crash report but no date
column, so we ask for one month at a time and tag each batch with its month.

Usage:
    pip install requests pandas
    python pg_crashes_by_month.py                     # Jan 2024 through current month
    python pg_crashes_by_month.py --county "Montgomery" --out mont_crashes.csv
"""

import argparse
import calendar
import io
import re
import time
from datetime import date

import pandas as pd
import requests

HOST = "https://analytics.mdsp.org"
VIEW = "/t/Public/views/PublicCrash2/PublicCrash"
VIZQL = "/vizql/t/Public/w/PublicCrash2/v/PublicCrash"
CRASH_MAP_SHEET = "{F0D0B632-0F6E-434B-A560-33264B170293}"  # "Crash Map" worksheet
EARLIEST = date(2024, 1, 1)  # dashboard only holds data from 2024 on

HEADERS = {
    "User-Agent": "Mozilla/5.0 (JOUR405 data class; contact dpwillis@umd.edu)",
    "X-Requested-With": "XMLHttpRequest",
}


def month_ranges(start: date, end: date):
    """Yield (first_day, last_day) for every month from start to end."""
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        last = date(y, m, calendar.monthrange(y, m)[1])
        yield date(y, m, 1), min(last, end)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def filter_params(county: str, begin: date, end: date) -> dict:
    return {
        "Crash County Description": county,
        "Crash Date Begin": begin.isoformat(),
        "Crash Date End": end.isoformat(),
    }


def expected_count(s: requests.Session, county: str, begin: date, end: date) -> int:
    """Total crashes the dashboard reports for this filter (for a sanity check)."""
    r = s.get(HOST + VIEW + ".csv", params=filter_params(county, begin, end), timeout=60)
    r.raise_for_status()
    summary = pd.read_csv(io.StringIO(r.text), thousands=",")
    return int(summary["Distinct count of Reportnumber"].sum())


def export_crash_map(s: requests.Session, county: str, begin: date, end: date) -> pd.DataFrame:
    """Open a filtered Tableau session and export the Crash Map sheet as a DataFrame."""
    # 1. Start a viewing session with the filters in the query string.
    params = {":embed": "y", **filter_params(county, begin, end)}
    r = s.post(HOST + VIZQL + "/startSession/viewing", params=params, timeout=60)
    r.raise_for_status()
    info = r.json()
    sid = info["sessionid"]

    # 2. Bootstrap it. showParams and stickySessionKey carry the URL filters;
    #    without them you get the dashboard's default (statewide, current year).
    form = {
        "sheet_id": info["sheetId"],
        "showParams": info["showParams"],
        "stickySessionKey": info["stickySessionKey"],
        "worksheetPortSize": '{"w":1280,"h":900}',
        "dashboardPortSize": '{"w":1280,"h":900}',
        "clientDimension": '{"w":1280,"h":900}',
        "renderMapsClientSide": "true",
        "isBrowserRendering": "true",
        "browserRenderingThreshold": "100",
        "formatDataValueLocally": "false",
        "navType": "Reload",
        "navSrc": "Top",
        "devicePixelRatio": "1",
        "language": "en",
        "locale": "en_US",
    }
    r = s.post(f"{HOST}{VIZQL}/bootstrapSession/sessions/{sid}",
               files={k: (None, v) for k, v in form.items()}, timeout=120)
    r.raise_for_status()

    # 3. Ask the server to build the crosstab CSV for the Crash Map sheet.
    export_form = {"sheetdocId": CRASH_MAP_SHEET, "useTabs": "true", "sendNotifications": "true"}
    r = s.post(f"{HOST}{VIZQL}/sessions/{sid}/commands/tabsrv/export-crosstab-to-csvserver",
               files={k: (None, v) for k, v in export_form.items()},
               headers={"X-Tsi-Active-Tab": "PublicCrash"}, timeout=300)
    r.raise_for_status()
    match = re.search(r'"resultKey":\s*"(\d+)"', r.text)
    if not match:
        raise RuntimeError(f"No export key returned: {r.text[:300]}")

    # 4. Download the file: UTF-16, tab-separated, despite the .csv name.
    r = s.get(f"{HOST}{VIZQL}/tempfile/sessions/{sid}",
              params={"key": match.group(1), "keepfile": "yes", "attachment": "yes"}, timeout=300)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), sep="\t", encoding="utf-16", dtype=str)

    # The map draws two layers, so each crash appears twice; the duplicate has
    # blank attribute columns. Keep the row that has the crash details.
    df = df[df["Crash Severity Description"].notna()].copy()
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--county", default="Prince George's")
    ap.add_argument("--start", default=EARLIEST.isoformat(), help="YYYY-MM-DD (default 2024-01-01)")
    ap.add_argument("--end", default=date.today().isoformat(), help="YYYY-MM-DD (default today)")
    ap.add_argument("--out", default="pg_crashes_2024_present.csv")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between months")
    args = ap.parse_args()

    start = max(date.fromisoformat(args.start), EARLIEST)
    end = date.fromisoformat(args.end)

    s = requests.Session()
    s.headers.update(HEADERS)

    frames = []
    for begin, finish in month_ranges(start, end):
        label = begin.strftime("%Y-%m")
        for attempt in range(3):
            try:
                df = export_crash_map(s, args.county, begin, finish)
                expected = expected_count(s, args.county, begin, finish)
                break
            except Exception as e:  # network hiccup or expired session: retry
                print(f"{label}: attempt {attempt + 1} failed ({e})")
                time.sleep(5)
        else:
            raise SystemExit(f"Giving up on {label}")

        flag = "" if len(df) == expected else f"  <-- MISMATCH, dashboard says {expected}"
        print(f"{label}: {len(df):>6,} crashes{flag}")
        df.insert(0, "month", label)
        frames.append(df)
        time.sleep(args.pause)

    crashes = pd.concat(frames, ignore_index=True)
    crashes = crashes.rename(columns={"Latitude (generated)": "Latitude",
                                      "Longitude (generated)": "Longitude"})
    crashes = crashes.drop(columns=["CrashPoint"], errors="ignore")

    dupes = crashes["Reportnumber"].duplicated().sum()
    if dupes:
        print(f"Note: {dupes} report numbers appear in more than one month")

    crashes.to_csv(args.out, index=False)
    print(f"\nWrote {len(crashes):,} crashes to {args.out}")


if __name__ == "__main__":
    main()
