#!/usr/bin/env python3
"""
Fetch Ottawa active MLS listings from realtor.ca via Apify scrapemind~realtor-ca-scraper.
Covers the full Ottawa-Gatineau region using 6 geographic tiles.

Outputs: ottawa-realtors.csv
  Agent Name, Agent Phone, Brokerage, Broker Phone, MLS ID,
  Address, City, Price, Beds, Baths, Detail URL

Usage:
  python3 fetch_ottawa_realtor_ca.py
"""

import csv
import json
import time
from pathlib import Path

import requests

APIFY_TOKEN = "YOUR_APIFY_TOKEN"  # set via env: export APIFY_TOKEN=apify_api_...
ACTOR_ID    = "scrapemind~realtor-ca-scraper"
BASE_URL    = "https://api.apify.com/v2"
OUT_CSV     = Path(__file__).parent / "ottawa-realtors.csv"

# ── Geographic tiles covering Ottawa-Gatineau (4 cols × 4 rows = 16 tiles) ────
# Each tile is (lat_max, lon_max, lat_min, lon_min, label)
# Ottawa full extent: lat 45.10–45.65, lon -75.20 to -76.05
# Ottawa full extent: lat 45.10–45.65, lon -75.20 (east) to -76.05 (west)
# lon_max is the EAST edge (less negative), lon_min is the WEST edge (more negative)
_LAT = [45.650, 45.512, 45.375, 45.237, 45.100]   # south → north slices
_LON = [-75.200, -75.412, -75.625, -75.837, -76.050]  # east → west slices
_ROW = ["north", "upper-mid", "lower-mid", "south"]
_COL = ["east", "central-east", "central-west", "west"]

TILES = [
    # lat_max, lon_max(east), lat_min, lon_min(west)
    (_LAT[r], _LON[c], _LAT[r+1], _LON[c+1], f"{_ROW[r]}-{_COL[c]}")
    for r in range(4) for c in range(4)
]

MAX_ITEMS_PER_TILE = 500


def realtor_url(lat_max, lon_max, lat_min, lon_min):
    return (
        "https://www.realtor.ca/map"
        f"#ZoomLevel=11"
        f"&Center={(lat_max+lat_min)/2:.5f}%2C{(lon_max+lon_min)/2:.5f}"
        f"&LatitudeMax={lat_max}&LongitudeMax={lon_max}"
        f"&LatitudeMin={lat_min}&LongitudeMin={lon_min}"
        f"&Sort=6-A&PropertyTypeGroupID=1&TransactionTypeId=2"
        f"&PropertySearchTypeId=0&Currency=CAD&RecordsPerPage=50"
        f"&ApplicationId=1&CultureId=1&Version=7.0&CurrentPage=1"
    )


def run_actor(url: str, max_items: int) -> str:
    resp = requests.post(
        f"{BASE_URL}/acts/{ACTOR_ID}/runs",
        params={"token": APIFY_TOKEN},
        json={"startUrls": [{"url": url}], "maxItems": max_items},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def wait_for_run(run_id: str, poll_secs: int = 10) -> str:
    while True:
        try:
            resp = requests.get(
                f"{BASE_URL}/actor-runs/{run_id}",
                params={"token": APIFY_TOKEN},
                timeout=20,
            )
            r = resp.json()["data"]
        except Exception:
            time.sleep(poll_secs)
            continue
        status = r["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            if status != "SUCCEEDED":
                raise RuntimeError(f"Run {run_id} ended with status {status}")
            return r["defaultDatasetId"]
        time.sleep(poll_secs)


def fetch_dataset(dataset_id: str) -> list:
    items, offset, limit = [], 0, 500
    while True:
        r = requests.get(
            f"{BASE_URL}/datasets/{dataset_id}/items",
            params={"token": APIFY_TOKEN, "offset": offset, "limit": limit},
            timeout=30,
        ).json()
        batch = r if isinstance(r, list) else r.get("items", [])
        if not batch:
            break
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return items


# ── Parsing ───────────────────────────────────────────────────────────────────
def parse_phone(phones: list) -> str:
    for p in phones or []:
        area = p.get("AreaCode", "")
        num  = p.get("PhoneNumber", "")
        if area and num:
            return f"{area}-{num}"
        if num:
            return num
    return ""


def parse_listing(item: dict) -> dict | None:
    individuals = item.get("Individual") or []
    if not individuals:
        return None
    ind  = individuals[0]
    org  = ind.get("Organization") or {}
    prop = item.get("Property") or {}
    bldg = item.get("Building") or {}
    addr = prop.get("Address") or {}

    agent_name  = ind.get("Name", "").strip()
    agent_phone = parse_phone(ind.get("Phones", []))
    brokerage   = org.get("Name", "").strip()
    broker_addr = org.get("Address") or {}
    broker_phone = parse_phone(org.get("Phones", []))

    address_text = addr.get("AddressText", "").strip()
    # "123 Main St|Ottawa, ON K1A 0A1" → split on |
    parts = address_text.split("|")
    street = parts[0].strip() if parts else address_text
    city_line = parts[1].strip() if len(parts) > 1 else ""
    city = city_line.split(",")[0].strip() if city_line else "Ottawa"

    price_raw = prop.get("Price", "")
    price_val = prop.get("PriceUnformattedValue", "") or price_raw

    beds = (bldg.get("Bedrooms") or bldg.get("BedroomsTotal") or "").strip()
    baths = (bldg.get("BathroomTotal") or bldg.get("Bathrooms") or "").strip()

    rel_url  = item.get("RelativeDetailsURL") or item.get("RelativeURLEn", "")
    full_url = f"https://www.realtor.ca{rel_url}" if rel_url else ""

    if not agent_name:
        return None

    return {
        "Agent Name":   agent_name,
        "Agent Phone":  agent_phone,
        "Brokerage":    brokerage,
        "Broker Phone": broker_phone,
        "MLS ID":       item.get("MlsNumber", ""),
        "Address":      street,
        "City":         city,
        "Price":        price_val,
        "Beds":         beds,
        "Baths":        baths,
        "Detail URL":   full_url,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    seen_mls = set()
    rows = []

    for lat_max, lon_max, lat_min, lon_min, label in TILES:
        url = realtor_url(lat_max, lon_max, lat_min, lon_min)
        print(f"\n[{label}] Starting actor run...", flush=True)

        run_id = run_actor(url, MAX_ITEMS_PER_TILE)
        print(f"  Run ID: {run_id} — waiting...", flush=True)

        dataset_id = wait_for_run(run_id)
        items = fetch_dataset(dataset_id)
        print(f"  Raw items: {len(items)}", flush=True)

        new = 0
        for item in items:
            row = parse_listing(item)
            if not row:
                continue
            mls = row["MLS ID"]
            if mls and mls in seen_mls:
                continue
            if mls:
                seen_mls.add(mls)
            rows.append(row)
            new += 1

        print(f"  New listings added: {new} (total so far: {len(rows)})", flush=True)

    # Write CSV
    fieldnames = ["Agent Name", "Agent Phone", "Brokerage", "Broker Phone",
                  "MLS ID", "Address", "City", "Price", "Beds", "Baths", "Detail URL"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\n✓ Saved {len(rows)} listings → {OUT_CSV}")


if __name__ == "__main__":
    main()
