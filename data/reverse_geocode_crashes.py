# /// script
# requires-python = ">=3.10"
# dependencies = ["geopandas", "pyogrio", "pandas", "shapely"]
# ///
"""
Add city and ZIP code columns to the PG County crash data using its lat/lng.

This does the lookup offline with point-in-polygon joins against Census
boundary files, so it handles all ~53,000 crashes in seconds instead of
hours of API calls.

  - city: the Census place the crash falls in. That covers incorporated
    cities and towns (College Park, Hyattsville, Bowie) and Census-designated
    places for unincorporated communities (Adelphi, Langley Park, Beltsville).
    Crashes outside any place are labeled "Unincorporated".
  - zip: the ZIP Code Tabulation Area (ZCTA), the Census approximation of a
    ZIP code. Points that fall just outside every ZCTA (water, highway
    edges) get the nearest one.

Note that a place name is not always the same as a mailing city:
much of "Hyattsville" by mailing address is unincorporated land.

Run with:
    uv run reverse_geocode_crashes.py
or pass input/output paths:
    uv run reverse_geocode_crashes.py pg_crashes_2024_present.csv pg_crashes_geocoded.csv
"""

import sys
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd

HERE = Path(__file__).parent
CACHE = HERE / "census_shapes"

PLACES_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_24_place_500k.zip"
ZCTA_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"


def download(url):
    """Download a Census shapefile zip once and reuse it after that."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / url.rsplit("/", 1)[1]
    if not path.exists():
        print(f"Downloading {url}")
        urllib.request.urlretrieve(url, path)
    return path


def main():
    infile = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "pg_crashes_2024_present.csv"
    outfile = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "pg_crashes_geocoded.csv"

    crashes = pd.read_csv(infile, dtype=str)
    lat = pd.to_numeric(crashes["Latitude"], errors="coerce")
    lng = pd.to_numeric(crashes["Longitude"], errors="coerce")
    has_coords = lat.notna() & lng.notna()
    print(f"{len(crashes):,} crashes, {(~has_coords).sum():,} without coordinates")

    points = gpd.GeoDataFrame(
        crashes.loc[has_coords, []],
        geometry=gpd.points_from_xy(lng[has_coords], lat[has_coords]),
        crs="EPSG:4326",
    )

    # Only load the boundaries that overlap the crash data
    bbox = tuple(points.total_bounds)

    places = gpd.read_file(download(PLACES_URL), bbox=bbox)
    places = places[["NAME", "NAMELSAD", "geometry"]].to_crs("EPSG:4326")
    places = places.rename(columns={"NAME": "city", "NAMELSAD": "city_type"})

    zctas = gpd.read_file(download(ZCTA_URL), bbox=bbox)
    zctas = zctas[["ZCTA5CE20", "geometry"]].to_crs("EPSG:4326")
    zctas = zctas.rename(columns={"ZCTA5CE20": "zip"})

    # Places don't overlap, so each point matches at most one
    with_city = gpd.sjoin(points, places, how="left", predicate="within")
    with_city = with_city[~with_city.index.duplicated()]

    # Use a projected CRS (Maryland State Plane, meters) for the nearest-ZCTA fallback
    with_zip = gpd.sjoin_nearest(points.to_crs("EPSG:26985"), zctas.to_crs("EPSG:26985"), how="left")
    with_zip = with_zip[~with_zip.index.duplicated()]

    crashes["city"] = with_city["city"].fillna("Unincorporated")
    crashes["city_type"] = with_city["city_type"]
    crashes["zip"] = with_zip["zip"]
    crashes.loc[~has_coords, "city"] = pd.NA

    crashes.to_csv(outfile, index=False)
    print(f"Wrote {outfile}")
    print(crashes["city"].value_counts(dropna=False).head(15).to_string())


if __name__ == "__main__":
    main()
