#!/usr/bin/env python3
"""
Enrich output/ottawa/envelopes/brokerage_addresses.csv
Uses DuckDuckGo search to find each brokerage's street address.
Run after generate_letters_ottawa.py.
"""

import csv
import re
import time
from pathlib import Path

CSV_PATH = Path("output/ottawa/envelopes/brokerage_addresses.csv")

POSTAL_RE = re.compile(r"([A-Z]\d[A-Z]\s*\d[A-Z]\d)", re.IGNORECASE)
PROV_RE   = re.compile(r",?\s*(?:Ontario|Quebec|ON|QC)\s*$", re.IGNORECASE)
SUITE_RE  = re.compile(r"^(?:Suite|Unit|Apt|#)\s*[\w\-]+\s*", re.IGNORECASE)
CITIES    = {"Ottawa", "Gatineau", "Nepean", "Kanata", "Barrhaven", "Orleans",
             "Gloucester", "Hull", "Aylmer", "Stittsville", "Manotick"}


def parse_address(text: str) -> dict:
    for m in POSTAL_RE.finditer(text):
        postal = m.group(1).replace(" ", "").upper()
        if postal[0] not in "ABCEGHJKLMNPRSTVXY":
            continue
        before = PROV_RE.sub("", text[max(0, m.start() - 150): m.start()]).strip(" ,")
        nums = list(re.finditer(r"\b(\d{2,5})\s+[A-Za-z]", before))
        if not nums:
            continue
        addr_chunk = before[nums[-1].start():].strip(" ,")
        if "," in addr_chunk:
            parts = addr_chunk.rsplit(",", 1)
            street = parts[0].strip().title()
            city   = SUITE_RE.sub("", parts[1].strip()).strip().title()
        else:
            street = addr_chunk.title()
            city   = "Ottawa"
        for cw in CITIES:
            if cw.lower() in city.lower():
                city = cw
                break
        if len(street) > 5 and len(city) > 2:
            return {"street_address": street, "city": city,
                    "postal_code": postal[:3] + " " + postal[3:]}
    return {}


def ddg_search(brokerage: str) -> dict:
    try:
        from ddgs import DDGS
        with DDGS() as d:
            results = list(d.text(f"{brokerage} realtor.ca address", max_results=5))
        for r in results:
            result = parse_address(r.get("body", "") + " " + r.get("title", ""))
            if result:
                return result
    except Exception:
        pass
    return {}


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found. Run generate_letters_ottawa.py first.")
        return

    rows  = list(csv.DictReader(CSV_PATH.open()))
    total = len(rows)
    found = 0

    for i, row in enumerate(rows, 1):
        brk = row["brokerage"]

        if row.get("street_address", "").strip():
            print(f"  [{i:02d}/{total}] SKIP — {brk[:50]}")
            found += 1
            continue

        print(f"  [{i:02d}/{total}] {brk[:55]} ...", end=" ", flush=True)
        result = ddg_search(brk)

        if result:
            row["street_address"] = result.get("street_address", "")
            row["city"]           = result.get("city", "")
            row["postal_code"]    = result.get("postal_code", "")
            found += 1
            print(f"✓  {row['street_address']}, {row['city']} {row['postal_code']}")
        else:
            print("— not found")

        time.sleep(0.8)

    fieldnames = ["brokerage", "street_address", "city", "province", "postal_code"]
    with CSV_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\n{found}/{total} enriched. Saved → {CSV_PATH}")


if __name__ == "__main__":
    main()
