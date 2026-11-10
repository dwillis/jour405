"""
Download every record from the Institute for Composer Diversity's
Orchestra Repertoire Search (https://www.composerdiversity.com/orchestra-repertoire-search)
and save them as JSON.

The search on that page is a Caspio DataPage. It works in two steps:
  1. POST the (empty) search form with AjaxAction=SearchForm -> returns an appSession
  2. POST AjaxAction=GetData with that appSession and CPIPage=N -> returns one page
     of results as JSON, with the result table as HTML in "responseText".
Each response hands back a new appSession, which is used for the next request.

Usage:
    uv run python scrape_orchestra_repertoire.py [output.json]
"""

import html
import json
import os
import sys
import time
from html.parser import HTMLParser

import requests

APP_KEY = "6bfa60001ee4394030fd48db9f3c"
ENDPOINT = f"https://c1abd369.caspio.com/dp/{APP_KEY}"
PAGE_URL = "https://www.composerdiversity.com/orchestra-repertoire-search"
PAGE_SIZE = 100  # rows per request
DELAY = 2  # seconds between requests, to be polite (~157 requests, ~5 minutes)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (data journalism class scraper)",
    "Origin": "https://www.composerdiversity.com",
    "Referer": PAGE_URL,
}

COMMON = {
    "ClientQueryString": "",
    "GridMode": "False",
    "js": "true",
    "PageID": "2",
    "AjaxActionHostName": "https://www.composerdiversity.com",
    "cbAjaxReferrer": PAGE_URL,
    "cbParamList": "",
}

# The empty search form, as the page submits it (no filters = all records).
SEARCH_FIELDS = {
    2: ("COMPOSER", "="),
    3: ("STATUS", "="),
    4: ("WMUC", "="),
    6: ("TITLE", "LIKE"),
    7: ("CON_CHAM", "="),
    8: ("INSTRUMENTS", "LIKE"),
    9: ("RANGES", "="),
    11: ("ORCHESTRA", "="),
}


def search_form_data():
    data = {
        "AppKey": APP_KEY,
        "PrevPageID": "1",
        "cbPageType": "Search",
        "pathname": PAGE_URL,
        "GlobalOperator": "AND",
        "NumCriteria": "11",
        "Search": "1",
        "AjaxAction": "SearchForm",
    }
    for n, (field, comparison) in SEARCH_FIELDS.items():
        data[f"FieldName{n}"] = field
        data[f"Operator{n}"] = "OR"
        data[f"NumCriteriaDetails{n}"] = "1"
        data[f"ComparisonType{n}_1"] = comparison
        data[f"MatchNull{n}_1"] = "N"
        data[f"Value{n}_1"] = ""
    data.update(COMMON)
    return data


class ResultTableParser(HTMLParser):
    """Pull header names and data rows out of Caspio's result table HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.headers, self.rows = [], []
        self._in_th = self._in_label = False
        self._cell = None
        self._row = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "th" and "cbResultSetHeaderCell" in cls:
            self._in_th, self._cell = True, ""
        elif tag == "tr" and a.get("data-cb-name") == "data":
            self._row = []
        elif tag == "td" and self._row is not None and "cbResultSetData" in cls:
            self._cell = ""
        elif tag == "span" and "data-tabular-html-cell-label" in a:
            self._in_label = True  # mobile label like "YEAR:"; skip it
        elif tag == "br" and self._cell is not None:
            self._cell += "\n"

    def handle_endtag(self, tag):
        if tag == "th" and self._in_th:
            self.headers.append(self._cell.strip())
            self._in_th, self._cell = False, None
        elif tag == "span" and self._in_label:
            self._in_label = False
        elif tag == "td" and self._row is not None and self._cell is not None:
            self._row.append(self._cell.replace("\xa0", " ").strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None and not self._in_label:
            self._cell += data


def parse_records(table_html):
    p = ResultTableParser()
    p.feed(html.unescape(table_html) if "&lt;table" in table_html else table_html)
    return [dict(zip(p.headers, row)) for row in p.rows]


class BlockedError(Exception):
    pass


def post(session, data):
    for attempt in range(3):
        try:
            r = session.post(ENDPOINT, data=data, headers=HEADERS, timeout=60)
        except requests.RequestException as e:
            print(f"  network error ({e}); retrying in {10 * (attempt + 1)}s", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
            continue
        # Caspio sits behind AWS WAF. If it decides we look like a bot it answers
        # 202 with an empty body and this header. Don't hammer it: stop and let
        # the user try again later (the script resumes from the saved file).
        if r.headers.get("x-amzn-waf-action"):
            raise BlockedError(
                f"Caspio's firewall returned a '{r.headers['x-amzn-waf-action']}' "
                "response. Wait a while (try again in an hour or so) and rerun; "
                "the script will pick up where it left off."
            )
        r.raise_for_status()
        return r.json()
    raise RuntimeError("giving up after 3 failed attempts")


def save(records, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def main(out_path="orchestra_repertoire.json"):
    s = requests.Session()

    # Resume from a partial file if one exists (pages are fixed-size and sorted).
    records = []
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            records = json.load(f)
        if records:
            print(f"Resuming: {len(records)} records already in {out_path}")
    page = len(records) // PAGE_SIZE + 1
    records = records[: (page - 1) * PAGE_SIZE]  # drop any partial last page

    try:
        # Step 1: submit the empty search to start a session.
        resp = post(s, search_form_data())
        app_session = resp["appSession"]
        time.sleep(DELAY)
        fetch_pages(s, app_session, records, page, out_path)
    except BlockedError as e:
        save(records, out_path)
        sys.exit(f"Stopped after {len(records)} records (saved to {out_path}).\n{e}")


def fetch_pages(s, app_session, records, page, out_path):
    total_pages = None
    while total_pages is None or page <= total_pages:
        data = {
            **COMMON,
            "appSession": app_session,
            "siblingDataPageAppSessions": "{}",
            "AjaxAction": "GetData",
            "cbCurrentPageSize": str(PAGE_SIZE),
            "CPIPage": str(page),
            "CPIOrderBy": "COMPOSER",
            "CPISortType": "asc",
        }
        resp = post(s, data)
        app_session = resp.get("appSession", app_session)
        total_pages = resp["totalPageCount"]
        batch = parse_records(resp["responseText"])
        records.extend(batch)
        print(f"page {page}/{total_pages}: {len(batch)} records "
              f"({len(records)}/{resp['totalRecords']})")
        if not batch:
            break
        if page % 10 == 0:
            save(records, out_path)  # checkpoint
        page += 1
        time.sleep(DELAY)

    if len(records) != resp["totalRecords"]:
        print(f"WARNING: got {len(records)} records, expected {resp['totalRecords']}",
              file=sys.stderr)

    save(records, out_path)
    print(f"Saved {len(records)} records to {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
