#!/usr/bin/env python3
"""
Saturn Star Movers — Envelope Generator
Ottawa-Gatineau Region

Generates print-ready #10 envelope PDFs for top-20% realtors.
One envelope per page (landscape, 9.5" × 4.125").

Run generate_letters_ottawa.py first (creates agent_summary.csv).

Output:
  output/ottawa/envelopes/ENVELOPES_TIER1.pdf
  output/ottawa/envelopes/ENVELOPES_ALL.pdf
"""

import io
import re
from pathlib import Path

import pandas as pd
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE       = Path(__file__).parent
OUT        = BASE / "output" / "ottawa"
EDIR       = OUT / "envelopes"
LOGO       = BASE / "logo.jpg"
STAMP      = BASE / "canada-post-stamp.jpeg"
AGENT_CSV  = OUT / "agent_summary.csv"
BROKER_CSV = OUT / "envelopes" / "brokerage_addresses.csv"

EDIR.mkdir(parents=True, exist_ok=True)

# ── Brand ─────────────────────────────────────────────────────────────────────
COMPANY   = "Saturn Star Movers"
RET_LINE1 = "Ottawa, ON"
RET_LINE2 = ""
PHONE     = "(226) 773-2993"

NAVY  = HexColor("#1a2744")
GRAY  = HexColor("#666666")
BLACK = HexColor("#111111")

ENV_W     = 9.5  * inch
ENV_H     = 4.125 * inch
PAGE_SIZE = (ENV_W, ENV_H)


def clean_name(agent_name: str) -> str:
    part = agent_name.strip().split(",")[0].strip()
    return re.sub(r"\s+", " ", part).strip(".")


def clean_brokerage(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip())
    while re.search(r"[Bb]rokerage [Bb]rokerage$", name):
        name = re.sub(r" [Bb]rokerage$", "", name).strip()
    return name


def draw_envelope(c: canvas.Canvas, agent_name: str, brokerage: str,
                  street: str = "", city: str = "", postal: str = ""):
    W, H = ENV_W, ENV_H
    pad  = 0.35 * inch
    ra_x = pad
    ra_y = H - pad

    if LOGO.exists():
        lsz = 0.5 * inch
        c.drawImage(str(LOGO), ra_x, ra_y - lsz,
                    width=lsz, height=lsz,
                    preserveAspectRatio=True, mask="auto")
        ra_y -= lsz + 4

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(NAVY)
    c.drawString(ra_x, ra_y, COMPANY)
    ra_y -= 11

    c.setFont("Helvetica", 7)
    c.setFillColor(GRAY)
    for line in filter(None, [RET_LINE1, RET_LINE2, PHONE]):
        c.drawString(ra_x, ra_y, line)
        ra_y -= 10

    rec_cx = W * 0.60
    rec_cy = H * 0.48

    display_name = clean_name(agent_name)
    display_brk  = clean_brokerage(brokerage)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLACK)
    name_w = c.stringWidth(display_name, "Helvetica-Bold", 11)
    c.drawString(rec_cx - name_w / 2, rec_cy + 14, display_name)

    c.setFont("Helvetica", 9.5)
    brk_w = c.stringWidth(display_brk, "Helvetica", 9.5)
    c.setFillColor(GRAY)
    c.drawString(rec_cx - brk_w / 2, rec_cy, display_brk)

    c.setFont("Helvetica", 8.5)
    addr_lines = []
    if street:
        addr_lines.append(street)
        addr_lines.append(f"{city}, ON  {postal}" if city else f"ON  {postal}")
    else:
        addr_lines = ["Street Address", "City, ON  Postal Code"]

    for i, line in enumerate(addr_lines):
        col = BLACK if street else HexColor("#bbbbbb")
        c.setFillColor(col)
        lw = c.stringWidth(line, "Helvetica", 8.5)
        c.drawString(rec_cx - lw / 2, rec_cy - 16 - i * 14, line)

    if STAMP.exists():
        stamp_w = 1.55 * inch
        stamp_h = 0.85 * inch
        c.drawImage(str(STAMP), W - stamp_w - 0.25 * inch, H - stamp_h - 0.18 * inch,
                    width=stamp_w, height=stamp_h,
                    preserveAspectRatio=True, mask="auto")

    c.setStrokeColor(HexColor("#dddddd"))
    c.setLineWidth(0.25)
    c.line(0, H - 0.06 * inch, W, H - 0.06 * inch)
    c.line(0, 0.06 * inch, W, 0.06 * inch)


def main():
    if not AGENT_CSV.exists():
        print("ERROR: agent_summary.csv not found. Run generate_letters_ottawa.py first.")
        return

    df    = pd.read_csv(AGENT_CSV).sort_values("rank").reset_index(drop=True)
    top20 = df.copy()
    tier1 = df[df["listings"] >= 10].copy()

    addr_map = {}
    no_addr  = set()
    if BROKER_CSV.exists():
        bdf = pd.read_csv(BROKER_CSV).fillna("")
        for _, r in bdf.iterrows():
            addr_map[r["brokerage"]] = {
                "street": str(r.get("street_address", "")),
                "city":   str(r.get("city", "")),
                "postal": str(r.get("postal_code", "")),
            }
            if not str(r.get("street_address", "")).strip():
                no_addr.add(r["brokerage"])
        print(f"Loaded {len(addr_map)} brokerage addresses.")

    before = len(top20)
    top20  = top20[~top20["brokerage"].isin(no_addr)].copy()
    tier1  = tier1[~tier1["brokerage"].isin(no_addr)].copy()
    if before - len(top20):
        print(f"  Removed {before - len(top20)} agents with no brokerage address.")

    def get_addr(brokerage):
        info = addr_map.get(brokerage, {})
        return info.get("street",""), info.get("city",""), info.get("postal","")

    print(f"Generating Tier-1 envelopes ({len(tier1)} agents)...")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE_SIZE)
    for _, row in tier1.iterrows():
        st, ct, po = get_addr(row["brokerage"])
        draw_envelope(c, row["agent_name"], row["brokerage"], st, ct, po)
        c.showPage()
    c.save()
    (EDIR / "ENVELOPES_TIER1.pdf").write_bytes(buf.getvalue())
    print("  ✓ ENVELOPES_TIER1.pdf")

    print(f"Generating all top-20% envelopes ({len(top20)} agents)...")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE_SIZE)
    for _, row in top20.iterrows():
        st, ct, po = get_addr(row["brokerage"])
        draw_envelope(c, row["agent_name"], row["brokerage"], st, ct, po)
        c.showPage()
    c.save()
    (EDIR / "ENVELOPES_ALL.pdf").write_bytes(buf.getvalue())
    print("  ✓ ENVELOPES_ALL.pdf")

    filled = sum(1 for _, r in top20.iterrows() if get_addr(r["brokerage"])[0])
    print(f"\n{filled}/{len(top20)} envelopes have full addresses.")
    print(f"Done. Envelopes in:\n  {EDIR}")


if __name__ == "__main__":
    main()
