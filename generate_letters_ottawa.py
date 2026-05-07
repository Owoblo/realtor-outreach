#!/usr/bin/env python3
"""
DEXA Movers — Realtor Partnership Letter Generator
Ottawa-Gatineau Region

Reads ottawa-realtors.csv, ranks all agents by listing count,
generates personalized PDF letters for the top 20%.

Output:
  output/ottawa/letters/01_FirstName_LastName.pdf  ← Tier 1 (10+ listings) individually
  output/ottawa/letters/ALL_TOP_20_PERCENT.pdf     ← all combined
  output/ottawa/agent_summary.csv
"""

import io
import re
from pathlib import Path

import pandas as pd
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter as LETTER_SIZE
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph, Spacer

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE  = Path(__file__).parent
DATA  = BASE / "ottawa-realtors.csv"
LOGO  = BASE / "dexa-logo.png"
OUT   = BASE / "output" / "ottawa"
LDIR  = OUT / "letters"
EDIR  = OUT / "envelopes"

for d in [LDIR, EDIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Brand ─────────────────────────────────────────────────────────────────────
COMPANY     = "DEXA Movers"
ADDR1       = "4108-1100 Canadian Shield Avenue"
ADDR2       = "Kanata, Ottawa, ON K2K 0K9"
PHONE       = "(613) 519-3236"
EMAIL       = "hello@dexamovers.ca"
PARTNER_URL = "dexamovers.ca/partners"
SENDER      = "The Team at DEXA Movers"
SENDER_TTL  = "DEXA Movers — Ottawa"
LETTER_DATE = "May 2026"
REGION      = "Ottawa"
CITIES_STR  = "Ottawa, Nepean, Kanata, Barrhaven, Orleans, and the surrounding area"

# ── Colours ───────────────────────────────────────────────────────────────────
NAVY  = HexColor("#253042")   # Dexa slate
GOLD  = HexColor("#b85718")   # Dexa copper
GRAY  = HexColor("#6e6459")   # Dexa stone
BLACK = HexColor("#19160f")   # Dexa ink

# ── Page geometry ─────────────────────────────────────────────────────────────
PW, PH   = LETTER_SIZE
ML = MR  = 66
MT = MB  = 54
TW       = PW - ML - MR

# ── Styles ────────────────────────────────────────────────────────────────────
def _s(name, font="Helvetica", size=9.5, lead=13.5, color=None,
        after=5, lindent=0, findent=0):
    return ParagraphStyle(name,
                          fontName=font, fontSize=size, leading=lead,
                          textColor=color or BLACK, spaceAfter=after,
                          alignment=TA_LEFT, leftIndent=lindent,
                          firstLineIndent=findent)

S = {
    "body":    _s("body"),
    "salut":   _s("salut",   font="Helvetica-Bold", after=8),
    "bullet":  _s("bullet",  after=3, lindent=16, findent=-16),
    "cta_ph":  _s("cta_ph",  font="Helvetica-Bold", size=11, lead=15, after=2),
    "cta_web": _s("cta_web", size=9.5, lead=13, after=6),
    "signame": _s("signame", font="Helvetica-Bold", after=0),
    "sigdet":  _s("sigdet",  size=9, lead=12, after=0),
    "ps":      _s("ps",      font="Helvetica-Oblique", size=8.5, lead=12,
                             color=GRAY, after=0),
}


def fmt(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


def extract_first(name: str) -> str:
    part = name.strip().split(",")[0].strip()
    return part.split()[0].strip(".")


def slugify(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name)
    return re.sub(r"\s+", "_", name.strip())


# ── Data Analysis ─────────────────────────────────────────────────────────────
def analyze(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["Agent Name"].notna() & (df["Agent Name"].str.strip() != "")]
    df["Price"]       = pd.to_numeric(df["Price"], errors="coerce").fillna(0)
    df["City"]        = df["City"].fillna("Ottawa").str.strip()
    df["Brokerage"]   = df["Brokerage"].fillna("Unknown").str.strip()
    df["Agent Name"]  = df["Agent Name"].str.strip()
    df["Agent Phone"] = df["Agent Phone"].fillna("").str.strip()

    rows = []
    for agent_name, grp in df.groupby("Agent Name"):
        prices = grp["Price"][grp["Price"] > 0]
        cities = grp["City"].value_counts()
        broker = grp["Brokerage"].mode()[0]

        top_addr, top_price = "", 0
        if len(prices) > 0:
            idx       = grp["Price"].idxmax()
            top_price = grp.loc[idx, "Price"]
            top_addr  = grp.loc[idx, "Address"]

        rows.append({
            "agent_name":        agent_name,
            "first_name":        extract_first(agent_name),
            "phone":             grp["Agent Phone"].iloc[0],
            "brokerage":         broker,
            "listings":          len(grp),
            "volume":            prices.sum() if len(prices) else 0,
            "median_price":      prices.median() if len(prices) else 0,
            "min_price":         prices.min() if len(prices) else 0,
            "max_price":         prices.max() if len(prices) else 0,
            "top_city":          cities.index[0] if len(cities) else "Ottawa",
            "top_city_n":        int(cities.iloc[0]) if len(cities) else 0,
            "city_spread":       list(cities.index[:3]),
            "city_pct":          cities.iloc[0] / len(grp) * 100 if len(grp) else 0,
            "top_listing_price": top_price,
            "top_listing_addr":  top_addr,
        })

    adf = pd.DataFrame(rows)

    brk = (df.groupby("Brokerage")
             .agg(brk_listings=("Agent Name", "count"),
                  brk_agents=("Agent Name", "nunique"))
             .reset_index()
             .rename(columns={"Brokerage": "brokerage"}))
    adf = adf.merge(brk, on="brokerage", how="left")
    adf["brk_pct"] = (adf["listings"] / adf["brk_listings"] * 100).round(1)

    adf = adf.sort_values("listings", ascending=False).reset_index(drop=True)
    adf["rank"]         = adf.index + 1
    adf["total_agents"] = len(adf)
    adf["percentile"]   = (adf["rank"] / len(adf) * 100).round(1)
    cutoff              = max(1, int(len(adf) * 0.20))
    adf["top20"]        = adf["rank"] <= cutoff

    return adf


# ── Letter Content ────────────────────────────────────────────────────────────
def build_story(a: dict, total_agents: int) -> list:
    first    = a["first_name"]
    rank     = int(a["rank"])
    n        = int(a["listings"])
    vol      = a["volume"]
    med      = a["median_price"]
    lo       = a["min_price"]
    hi       = a["max_price"]
    pct      = a["percentile"]
    below    = total_agents - rank
    brok     = a["brokerage"]
    brk_pct  = a["brk_pct"]
    brk_n    = int(a["brk_agents"])
    top_c    = a["top_city"]
    city_n   = int(a["top_city_n"])
    cities   = a["city_spread"]
    city_pct = a["city_pct"]
    hi_price = a["top_listing_price"]

    story = []

    story.append(Paragraph(
        "I went through every active residential listing across Ottawa and the "
        "surrounding area. Every agent, every brokerage, every neighbourhood — "
        "from Kanata to Orleans, Barrhaven to Rockcliffe. And your name kept coming up.",
        S["body"]))

    story.append(Paragraph(
        f"Out of <b>{total_agents:,} licensed agents</b> active in this market, you rank "
        f"<b>#{rank}</b>. That puts you in the <b>top {pct:.1f}%</b> of every agent "
        f"working Ottawa right now. <b>{below:,} agents</b> are behind you.",
        S["body"]))

    vol_line = (f"<b>{n} active listing{'s' if n != 1 else ''}. "
                f"{fmt(vol)} in estimated portfolio value.</b> "
                f"Median listing price of <b>{fmt(med)}</b>")
    if n >= 3:
        vol_line += f", with a range from <b>{fmt(lo)}</b> to <b>{fmt(hi)}</b>."
    else:
        vol_line += "."
    story.append(Paragraph(vol_line, S["body"]))

    if brk_pct >= 30:
        story.append(Paragraph(
            f"You personally account for <b>{brk_pct:.0f}%</b> of "
            f"<b>{brok}</b>'s entire listing inventory. "
            f"{'There is' if brk_n == 1 else f'There are {brk_n} agents'} from your "
            f"brokerage in the top tier, and you're carrying the weight.",
            S["body"]))
    elif brk_pct >= 10:
        story.append(Paragraph(
            f"You represent <b>{brk_pct:.0f}%</b> of {brok}'s active listings — "
            f"one of the top producers in an office of {brk_n} agents.",
            S["body"]))

    if len(cities) >= 2:
        if city_pct >= 80:
            geo = f"Your portfolio is concentrated in <b>{top_c}</b>. You own that market."
        elif city_pct >= 50:
            others = ", ".join([c for c in cities if c != top_c][:2])
            geo = (f"<b>{city_n} of your {n} listing{'s' if n != 1 else ''}</b> are in "
                   f"{top_c}, but you're also active in {others}. "
                   f"That kind of range tells me you're not a one-neighbourhood agent.")
        else:
            city_str = ", ".join(cities[:3])
            geo = (f"You're active across <b>{city_str}</b> — median listing of "
                   f"<b>{fmt(med)}</b>, range from {fmt(lo)} to {fmt(hi)}. "
                   f"You serve the full Ottawa market.")
        story.append(Paragraph(geo, S["body"]))

    if n >= 5 and hi_price > 0:
        story.append(Paragraph(
            f"Your highest listing sits at <b>{fmt(hi_price)}</b>. "
            f"The family spending {fmt(hi_price)} on a home in Ottawa expects the move "
            f"to be organized, professional, and completely stress-free.",
            S["body"]))

    story.append(Paragraph(
        f"That's not a small thing. In a market of {total_agents:,} agents, most are "
        f"working with a handful of listings. You're operating at a different level, "
        f"and that doesn't happen by accident.",
        S["body"]))

    story.append(Paragraph(
        "DEXA Movers is an Ottawa-based moving company built around one idea: "
        "every move your clients make should reflect the care you put into finding "
        "their home. We handle local and long-distance moves across Ottawa — "
        "full-service packing, wrapping, and furniture assembly. "
        "Every job carries <b>$2M in liability coverage</b>. "
        "I'm reaching out because I think we'd be a strong fit for your clients.",
        S["body"]))

    story.append(Paragraph("Here's what I'd offer your clients, exclusively through you:", S["body"]))

    bullets = [
        "<b>15% off their move</b> when referred by you",
        "Full-service packing, wrapping, and furniture assembly available",
        "A <b>dedicated move coordinator</b> for every job — one number for your client to call",
        "Real-time updates on move day so neither of you is left guessing",
        "<b>Priority scheduling</b> around closing dates whenever possible",
    ]
    for b in bullets:
        story.append(Paragraph(f"•   {b}", S["bullet"]))

    story.append(Paragraph(
        "When one of your clients needs moving support, send them our number "
        "or submit their details through our partner page:",
        S["body"]))
    story.append(Paragraph(PHONE, S["cta_ph"]))
    story.append(Paragraph(PARTNER_URL, S["cta_web"]))
    story.append(Paragraph(
        "We'll tag the referral under your name, apply the preferred client discount, "
        "and handle everything from quote to move day. No paperwork. No pressure.",
        S["body"]))

    story.append(Paragraph("Best,", S["body"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>{SENDER}</b>", S["signame"]))
    story.append(Paragraph(SENDER_TTL, S["sigdet"]))
    story.append(Paragraph(f"{PHONE} | {EMAIL}", S["sigdet"]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<i>P.S. — I already work with agents at your level in other Ontario markets. "
        f"Happy to share what's been working for them. No strings.</i>",
        S["ps"]))

    return story


# ── Header ────────────────────────────────────────────────────────────────────
HEADER_H = 90

def draw_header(c: canvas.Canvas):
    y = PH - MT

    if LOGO.exists():
        lsz = 78
        c.drawImage(str(LOGO), PW - MR - lsz, y - lsz,
                    width=lsz, height=lsz,
                    preserveAspectRatio=True, mask="auto")

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(NAVY)
    c.drawString(ML, y - 14, COMPANY)

    c.setFont("Helvetica", 8.5)
    c.setFillColor(GRAY)
    c.drawString(ML, y - 27, ADDR1)
    if ADDR2:
        c.drawString(ML, y - 38, ADDR2)
    offset = 38 if not ADDR2 else 49
    c.drawString(ML, y - offset, PHONE)
    c.drawString(ML, y - (offset + 11), EMAIL)

    rule_y = y - 70
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.5)
    c.line(ML, rule_y, ML + TW, rule_y)

    date_y = rule_y - 16
    c.setFont("Helvetica", 10)
    c.setFillColor(BLACK)
    c.drawString(ML, date_y, LETTER_DATE)

    salut_y = date_y - 22
    return salut_y


def draw_one_letter(c: canvas.Canvas, a: dict, total_agents: int):
    salut_y = draw_header(c)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(BLACK)
    c.drawString(ML, salut_y, f"Dear {a['first_name']},")

    body_top_y = salut_y - 18
    frame_h    = body_top_y - MB

    story = build_story(a, total_agents)
    f = Frame(ML, MB, TW, frame_h,
              leftPadding=0, rightPadding=0,
              topPadding=0, bottomPadding=0,
              showBoundary=0)
    f.addFromList(story, c)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not DATA.exists():
        print(f"ERROR: {DATA} not found. Run fetch_ottawa_realtor_ca.py first.")
        return

    print("Loading data...")
    adf          = analyze(DATA)
    total_agents = len(adf)
    top20        = adf[adf["top20"]].copy()
    tier1        = top20[top20["listings"] >= 10].copy()

    BROKER_CSV = OUT / "envelopes" / "brokerage_addresses.csv"
    if BROKER_CSV.exists():
        bdf = pd.read_csv(BROKER_CSV).fillna("")
        no_addr = set(bdf[bdf["street_address"].str.strip() == ""]["brokerage"])
        before = len(top20)
        top20 = top20[~top20["brokerage"].isin(no_addr)].copy()
        tier1 = tier1[~tier1["brokerage"].isin(no_addr)].copy()
        if before - len(top20):
            print(f"  Removed {before - len(top20)} agents (no brokerage address)")

    print(f"  Total agents  : {total_agents}")
    print(f"  Top 20%       : {len(top20)} agents")
    print(f"  Tier 1 (10+)  : {len(tier1)} agents")

    cols = ["rank", "agent_name", "first_name", "brokerage", "phone",
            "listings", "volume", "median_price", "top_city",
            "percentile", "brk_pct", "brk_agents"]
    top20[cols].to_csv(OUT / "agent_summary.csv", index=False)
    print("\nSaved agent_summary.csv")

    print(f"\nGenerating {len(tier1)} individual Tier-1 letters...")
    for _, row in tier1.iterrows():
        rank      = int(row["rank"])
        name_part = row["agent_name"].split(",")[0].strip()
        fname     = f"{rank:02d}_{slugify(name_part)}.pdf"
        buf       = io.BytesIO()
        c         = canvas.Canvas(buf, pagesize=LETTER_SIZE)
        draw_one_letter(c, row.to_dict(), total_agents)
        c.save()
        (LDIR / fname).write_bytes(buf.getvalue())
        print(f"  ✓ {fname}")

    print(f"\nGenerating combined PDF ({len(top20)} letters)...")
    buf = io.BytesIO()
    c   = canvas.Canvas(buf, pagesize=LETTER_SIZE)
    for _, row in top20.iterrows():
        draw_one_letter(c, row.to_dict(), total_agents)
        c.showPage()
    c.save()
    (LDIR / "ALL_TOP_20_PERCENT.pdf").write_bytes(buf.getvalue())
    print("  ✓ ALL_TOP_20_PERCENT.pdf")

    print(f"\nDone. Files in:\n  {LDIR}")


if __name__ == "__main__":
    main()
