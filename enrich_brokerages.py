#!/usr/bin/env python3
"""
Enrich brokerage_addresses.csv using OpenStreetMap Nominatim.
No API key needed. Searches brokerage name + Ontario context.
"""

import csv
import re
import time
import requests
from pathlib import Path

CSV_PATH = Path("output/windsor/envelopes/brokerage_addresses.csv")

HEADERS = {
    "User-Agent": "SaturnStarMovers-OutreachTool/1.0 (business@starmovers.ca)",
    "Accept-Language": "en",
}

# Known Windsor-area cities for context
CITIES = ["Windsor", "LaSalle", "Leamington", "Kingsville", "Amherstburg",
          "Chatham", "Lakeshore", "Essex", "Tecumseh", "Belle River"]


def clean_name(name: str) -> str:
    name = re.sub(r"\s+Brokerage$", "", name.strip(), flags=re.IGNORECASE)
    name = re.sub(r"\bBrokerage\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\bInc\.?\b|\bLtd\.?\b|\bLtd\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" .,")
    return name


def nominatim_search(query: str, country: str = "Canada") -> dict:
    params = {
        "q":              f"{query}, Ontario, {country}",
        "format":         "json",
        "addressdetails": 1,
        "limit":          3,
        "countrycodes":   "ca",
    }
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params, headers=HEADERS, timeout=10
        )
        results = r.json()
    except Exception:
        return {}

    for res in results:
        addr = res.get("address", {})
        road    = addr.get("road", "")
        house   = addr.get("house_number", "")
        city    = (addr.get("city") or addr.get("town") or
                   addr.get("village") or addr.get("municipality") or
                   addr.get("county", ""))
        postal  = addr.get("postcode", "")
        state   = addr.get("state", "")

        if "Ontario" not in state and "ON" not in state:
            continue
        if road:
            street = f"{house} {road}".strip() if house else road
            return {"street_address": street, "city": city, "postal_code": postal}

    return {}


def enrich(brokerage: str) -> dict:
    base = clean_name(brokerage)

    # Try full name first
    result = nominatim_search(base)
    if result:
        return result

    # Try with Windsor context
    result = nominatim_search(f"{base} Windsor")
    if result:
        return result

    # Try each city
    for city in CITIES:
        result = nominatim_search(f"{base} {city}")
        if result:
            return result

    # Strip to first meaningful words (brand name only)
    short = " ".join(base.split()[:4])
    result = nominatim_search(f"{short} real estate Windsor")
    if result:
        return result

    return {}


def main():
    rows = list(csv.DictReader(CSV_PATH.open()))
    total = len(rows)
    found = 0

    for i, row in enumerate(rows, 1):
        brk = row["brokerage"]

        if row.get("street_address", "").strip():
            print(f"  [{i:02d}/{total}] SKIP — {brk[:50]}")
            found += 1
            continue

        print(f"  [{i:02d}/{total}] {brk[:55]} ...", end=" ", flush=True)
        result = enrich(brk)

        if result:
            row["street_address"] = result.get("street_address", "")
            row["city"]           = result.get("city", "")
            row["postal_code"]    = result.get("postal_code", "")
            found += 1
            print(f"✓  {row['street_address']}, {row['city']} {row['postal_code']}")
        else:
            print("— not found")

        time.sleep(1.1)  # Nominatim rate limit: 1 req/sec

    fieldnames = ["brokerage", "street_address", "city", "province", "postal_code"]
    with CSV_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\n{found}/{total} enriched. Saved → {CSV_PATH}")


if __name__ == "__main__":
    main()
