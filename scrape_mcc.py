#!/usr/bin/env python3
"""
MCC Thunder scorebug builder.

Scrapes the composite calendar at https://mccthunder.com/calendar and renders a
board for embedding in a Populi News post.

The homepage carries the same markup but only a rolling six-row window, which
drops results within a day or two and cannot reliably supply "the most recent
finished games". The calendar carries the whole season in identical row markup,
so the parser accepts either and the calendar is the default.

Populi's News editor strips the src attribute off iframes on save (verified
2026-08-31), but leaves external <img src> untouched. So the delivery format is a
PNG, hot-linked from a News post. Regenerate the PNG at the same URL and every
page load picks up the current scores; the post itself is never touched again.

Usage:
    python3 scrape_mcc.py                         # scrape live, write ./index.html
    python3 scrape_mcc.py --png scorebug.png      # also render the PNG
    python3 scrape_mcc.py --out /tmp/sb.html      # choose output path
    python3 scrape_mcc.py --json                  # print parsed events, no render
    python3 scrape_mcc.py --from-file page.html   # parse a saved copy (offline test)
    python3 scrape_mcc.py --png scorebug.png --s3-png s3://mcc-scorebug/scorebug.png

Production is the last form: render the PNG and push it to the bucket.

The DOM contract (Drupal 8, same rows on the homepage and the calendar):

    div.view-event-schedule
      div.views-row
        span.day  span.month  span.date      -> date block
        div.logo > img[src]                  -> opponent logo
        div.site                             -> "VS." or "AT"
        div.sport                            -> "WOMENS VOLLEYBALL"
        div.opponent                         -> "DALLAS CHRISTIAN COLLEGE"
        div.city                             -> "MANHATTAN, KAN."
        div.result                           -> "W, 3-2"   (played games)
        div.time                             -> "5:00 PM"  (upcoming games)
        div.live-video > a[href]             -> YouTube stream link

If PressboxU restyles the site, this is the block to re-verify.
"""

import argparse
import html
import json
import pathlib
import re
import subprocess
import sys
import tempfile
from datetime import date as _date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://mccthunder.com/calendar"
SITE_URL = "https://mccthunder.com/"
SITE_ROOT = "https://mccthunder.com"
TZ = ZoneInfo("America/Chicago")
# Drop a higher-resolution <code>.png here (code = the athletics site's filename,
# e.g. sterlc, cottey, dallch) and it is used instead of the site's 70px version.
LOGO_DIR = pathlib.Path(__file__).parent / "logos"
# The Thunder banner mark. It ships with white around it, which is why the header
# is a white band rather than navy: the shield is navy and would sink into the
# primary colour otherwise.
BRAND_LOGO = LOGO_DIR / "mcc-thunder.png"
# Scores you know before the athletics site posts them. Each entry names a game
# and supplies a result; see apply_overrides() for the matching rules.
OVERRIDES = pathlib.Path(__file__).parent / "overrides.json"
USER_AGENT = "MCC-Populi-Scorebug/1.0 (+internal IT; contact MCC IT)"

# MCC brand palette.
NAVY = "#002052"        # primary
GRAY = "#ADAFB1"        # alternate
LIGHT = "#A3BCDB"       # tertiary
WHITE = "#FFFFFF"       # accent

# Everything else is one of the four, tinted with white or black over the navy,
# so no fifth hue enters the design.
SURFACE = "rgba(255, 255, 255, .11)"   # tile ground, a lift off the primary
SURFACE_DIM = "rgba(0, 0, 0, .18)"     # upcoming games, a step back
HOVER = "rgba(255, 255, 255, .13)"
RULE = "rgba(173, 175, 177, .5)"       # GRAY at half strength

BLACK = "#000000"

# Result chips: a white square with a navy W, a black square with a tertiary L.
# The letter carries the meaning, so no red or green is needed.
WIN_BG, WIN_FG = WHITE, NAVY
LOSS_BG, LOSS_FG = BLACK, LIGHT
TIE_BG, TIE_FG = GRAY, NAVY


# --------------------------------------------------------------------------
# scrape
# --------------------------------------------------------------------------

def fetch(url=SOURCE_URL):
    resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.text


def _text(row, class_name):
    el = row.find(class_=class_name)
    if not el:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def parse(markup):
    """Return a list of event dicts from the homepage markup."""
    soup = BeautifulSoup(markup, "html.parser")
    # The homepage wraps its six-row window in .view-event-schedule; the composite
    # calendar lists the whole season as bare .views-row siblings. Same row markup
    # either way, so accept both and let the caller choose the source.
    block = soup.find(class_="view-event-schedule") or soup
    rows = [r for r in block.find_all(class_="views-row") if r.find(class_="sport")]
    if not rows:
        raise RuntimeError(
            "Found no event rows with a .sport field. The athletics site layout "
            "probably changed; re-check the DOM contract in this file's docstring."
        )

    events = []
    for row in rows:
        img = row.find("img")
        logo = img.get("src") if img else ""
        code = pathlib.Path(logo).stem if logo else ""
        # A hand-placed logos/<code>.png wins over the athletics site's 70px mark.
        override = LOGO_DIR / f"{code}.png" if code else None
        if override and override.exists():
            logo = override.as_posix()
        elif logo.startswith("/"):
            logo = SITE_ROOT + logo

        link = ""
        live = row.find(class_="live-video")
        if live and live.find("a"):
            link = live.find("a").get("href", "")

        result = _text(row, "result")
        events.append(
            {
                "day": _text(row, "day"),
                "month": _text(row, "month"),
                "date": _text(row, "date"),
                "site": _text(row, "site") or "VS.",
                "sport": _text(row, "sport"),
                "opponent": _text(row, "opponent"),
                "city": _text(row, "city"),
                "result": result,
                "time": _text(row, "time"),
                "logo": logo,
                "link": link,
                "played": bool(result),
            }
        )

    return events


MONTHS = {m: i + 1 for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def event_date(ev, today):
    """The site prints no year, so pick the reading closest to today.

    A season straddles the new year, so a bare "JAN 10" seen in December is next
    month, not eleven months ago. Trying the neighbouring years and keeping the
    nearest gets that right without hardcoding season boundaries.
    """
    month = MONTHS.get(ev["month"][:3].upper())
    if not month or not ev["date"].isdigit():
        return None
    day = int(ev["date"])
    best = None
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            cand = _date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((cand - today).days) < abs((best - today).days):
            best = cand
    return best


def merge_multiday(events):
    """Collapse a multi-day event into one panel.

    Golf plays the same course on consecutive days and the site lists each day
    separately, which burns two of six panels on one tournament. Same sport, same
    opponent, same home/away, consecutive dates and both unplayed collapse into a
    single entry with a date range.
    """
    merged = []
    for ev in events:
        prev = merged[-1] if merged else None
        same = (
            prev
            and not prev["played"] and not ev["played"]
            and (prev["sport"], prev["opponent"], prev["site"])
            == (ev["sport"], ev["opponent"], ev["site"])
            and prev.get("dt") and ev.get("dt")
            and 0 <= (ev["dt"] - prev["dt"]).days <= 1
        )
        if same:
            prev["date_end"] = ev["date"]
            prev["dt_end"] = ev["dt"]
            continue
        merged.append(dict(ev))
    return merged


def select(events, today, recent_n, next_n):
    """Most recent finished games, then the next fixtures, by date.

    Going by date rather than by position in the feed matters because an event
    with no win/loss to report, a cross country meet say, otherwise looks
    "upcoming" forever and clogs the board after it has been run.
    """
    for ev in events:
        ev["dt"] = event_date(ev, today)

    played = sorted((e for e in events if e["played"] and e["dt"]),
                    key=lambda e: e["dt"])
    ahead = sorted((e for e in events if not e["played"] and e["dt"] and e["dt"] >= today),
                   key=lambda e: e["dt"])
    ahead = merge_multiday(ahead)

    total = recent_n + next_n
    take_recent = min(len(played), recent_n)
    take_next = min(len(ahead), total - take_recent)
    if take_recent + take_next < total:
        take_recent = min(len(played), total - take_next)

    return played[len(played) - take_recent:] + ahead[:take_next]


def apply_overrides(events, path=OVERRIDES):
    """Fill in results the athletics site has not published yet.

    The site can lag a final by hours, so this lets a known score go up
    immediately. An override applies ONLY to a game the site still shows as
    unplayed: the moment the site publishes its own result, the site wins and the
    override becomes inert. That way a stale entry cannot contradict the source
    of truth, and forgetting to clean up costs nothing.

    Matching is on month + date + a case-insensitive substring of the opponent,
    so "BETHANY" matches "BETHANY COLLEGE (KAN.)".
    """
    if not path.exists():
        return events

    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"warning: ignoring {path.name}, invalid JSON ({exc})", file=sys.stderr)
        return events

    for rule in rules:
        month = str(rule.get("month", "")).strip().upper()
        date = str(rule.get("date", "")).strip()
        opponent = str(rule.get("opponent", "")).strip().upper()
        result = str(rule.get("result", "")).strip()
        if not result:
            continue

        for ev in events:
            if ev["played"]:
                continue  # the site has spoken; leave it alone
            if month and ev["month"].upper() != month:
                continue
            if date and ev["date"] != date:
                continue
            if opponent and opponent not in ev["opponent"].upper():
                continue
            ev["result"] = result
            ev["time"] = ""
            ev["played"] = True
            ev["overridden"] = True
            print(f"override: {ev['month']} {ev['date']} {ev['opponent']} -> {result}")
            break

    return events


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

def _outcome(result):
    """'W, 3-2' -> ('W', '3-2'). Returns (None, result) if it doesn't parse."""
    m = re.match(r"\s*([WLT])\s*,\s*(.+)", result, re.I)
    if not m:
        return None, result
    return m.group(1).upper(), m.group(2).strip()


def _row_html(ev):
    e = lambda s: html.escape(s or "")

    if ev["played"]:
        letter, score = _outcome(ev["result"])
        cls = {"W": "win", "L": "loss"}.get(letter, "tie")
        badge = (
            f'<span class="badge {cls}">{e(letter or "")}</span>'
            f'<span class="score">{e(score)}</span>'
        )
    else:
        badge = f'<span class="upcoming">{e(ev["time"]) or "TBA"}</span>'

    logo = (
        f'<img class="logo" src="{e(ev["logo"])}" alt="" loading="lazy" '
        f"onerror=\"this.style.visibility='hidden'\">"
        if ev["logo"]
        else '<span class="logo logo-blank"></span>'
    )

    inner = f"""      <div class="date">
        <span class="dow">{e(ev["day"][:3])}</span>
        <span class="mon">{e(ev["month"])}</span>
        <span class="num">{e(ev["date"])}</span>
      </div>
      {logo}
      <div class="meta">
        <div class="sport">{e(ev["sport"])}</div>
        <div class="opp"><span class="site">{e(ev["site"])}</span> {e(ev["opponent"])}</div>
        <div class="city">{e(ev["city"])}</div>
      </div>
      <div class="outcome">{badge}</div>"""

    if ev["link"]:
        return f'    <a class="row" href="{e(ev["link"])}" target="_blank" rel="noopener">\n{inner}\n    </a>'
    return f'    <div class="row">\n{inner}\n    </div>'


def strip_css(tiles):
    """Size the strip for the number of panels.

    Five panels sit at about 142px each and everything fits comfortably. Six
    drops that to about 118px, which is too narrow for 11px type beside a 32px
    logo, so the type, mark and gaps all step down and names get a fourth line.
    The total height still has to land at or under Populi's 146px feed clip, so
    the header gives back a few pixels to pay for the taller name block.
    """
    if tiles >= 6:
        gap, pad, tile_h, brand_h = 5, 8, 86, 28
        logo, logo_gap, name_fs, clamp = 26, 6, 10, 4
    else:
        gap, pad, tile_h, brand_h = 6, 9, 84, 30
        logo, logo_gap, name_fs, clamp = 32, 8, 11, 3
    return f"""
  *, *::before, *::after {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    font-family: Kanit, "Helvetica Neue", Arial, sans-serif;
    background: {NAVY}; color: {WHITE}; -webkit-font-smoothing: antialiased;
  }}
  /* Total height must stay at or under 146px: that is the max-height Populi's
     .truncation_block puts on a news item in the Home feed. */
  .wrap {{ width: 760px; }}

  header {{
    display: flex; align-items: center; gap: 10px;
    background: {WHITE}; padding: 5px 12px;
    border-bottom: 3px solid {LIGHT};
  }}
  header .brand {{ height: {brand_h}px; width: auto; display: block; }}
  header .tag {{
    font-size: 10px; font-weight: 600; letter-spacing: .16em;
    color: {NAVY}; text-transform: uppercase;
    padding-left: 10px; border-left: 1px solid {GRAY};
  }}
  header .stamp {{ margin-left: auto; font-size: 9px; color: rgba(0, 32, 82, .55); }}

  .tiles {{ display: flex; gap: {gap}px; padding: 8px 12px 10px; }}
  .tile {{
    flex: 1 1 0; min-width: 0; height: {tile_h}px; overflow: hidden;
    background: {SURFACE}; border-top: 2px solid {LIGHT};
    padding: 6px {pad}px 9px; display: flex; flex-direction: column;
  }}
  .tile.next {{ border-top-color: {RULE}; background: {SURFACE_DIM}; }}

  .tile .sport {{
    font-size: 8px; letter-spacing: .1em; text-transform: uppercase;
    color: {LIGHT}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    flex: 0 0 auto;
  }}
  .tile.next .sport {{ color: {GRAY}; }}

  /* 32px slot: the site's logos are 70px, so this stays crisp at 2x and no
     larger. Anything above 35px starts upscaling. */
  /* min-height:0 lets the name block shrink instead of shoving the sport
     label out of the top of a fixed-height tile. */
  .who {{
    display: flex; align-items: center; gap: {logo_gap}px; margin-top: 4px;
    flex: 1 1 auto; min-height: 0;
  }}
  .who img {{ flex: 0 0 {logo}px; width: {logo}px; height: {logo}px; object-fit: contain; }}
  .who .nm {{
    font-size: {name_fs}px; font-weight: 600; line-height: 1.1; text-transform: uppercase;
    display: -webkit-box; -webkit-line-clamp: {clamp}; -webkit-box-orient: vertical; overflow: hidden;
  }}
  .who .nm .site {{ color: {LIGHT}; font-weight: 400; }}

  .line {{ display: flex; align-items: center; gap: 5px; white-space: nowrap; flex: 0 0 auto; }}
  .line .when {{ font-size: 9px; color: {LIGHT}; letter-spacing: .04em; }}
  .badge {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 15px; height: 15px; border-radius: 2px;
    font-size: 10px; font-weight: 700; line-height: 1;
  }}
  .badge.win {{ background: {WIN_BG}; color: {WIN_FG}; }}
  .badge.loss {{ background: {LOSS_BG}; color: {LOSS_FG}; }}
  .badge.tie {{ background: {TIE_BG}; color: {TIE_FG}; }}
  .score {{ font-size: 13px; font-weight: 700; }}
  .at {{ font-size: 12px; font-weight: 600; color: {WHITE}; margin-left: auto; }}
"""




SPORT_SHORT = (("WOMENS ", "W "), ("MENS ", "M "))
SPORT_COMBINED = "M/W CROSS COUNTRY"


def _sport_label(sport, tiles):
    """Full name at five panels, abbreviated at six.

    A six-wide strip leaves about 102px of text per tile, which truncates
    "WOMENS CROSS COUNTRY" mid-word. "W CROSS COUNTRY" fits and still reads.
    """
    if "CROSS COUNTRY," in sport or sport.count("CROSS COUNTRY") > 1:
        return SPORT_COMBINED
    if tiles < 6:
        return sport
    label = sport
    for long, short in SPORT_SHORT:
        if label.startswith(long):
            label = short + label[len(long):]
            break
    return label


def _tile_html(ev, tiles=5):
    e = lambda s: html.escape(s or "")
    logo = (
        f'<img src="{e(ev["logo"])}" alt="" onerror="this.style.visibility=\'hidden\'">'
        if ev["logo"]
        else ""
    )
    if ev.get("date_end"):
        # Weekday is dropped: "SEP 14-15" says more in less room than "MON SEP 14".
        when = f'{e(ev["month"])} {e(ev["date"])}-{e(ev["date_end"])}'
    else:
        when = f'{e(ev["day"][:3])} {e(ev["month"])} {e(ev["date"])}'

    if ev["played"]:
        letter, score = _outcome(ev["result"])
        cls = {"W": "win", "L": "loss"}.get(letter, "tie")
        foot = (
            f'<span class="when">{when}</span>'
            f'<span class="badge {cls}">{e(letter or "")}</span>'
            f'<span class="score">{e(score)}</span>'
        )
        kind = ""
    else:
        # The site writes 12:00 AM for events with no announced start time.
        t = ev["time"]
        if not t or t.strip() in ("12:00 AM", "12:00AM"):
            t = "TBA"
        foot = (
            f'<span class="when">{when}</span>'
            f'<span class="at">{e(t)}</span>'
        )
        kind = " next"

    return f"""    <div class="tile{kind}">
      <div class="sport">{e(_sport_label(ev["sport"], tiles))}</div>
      <div class="who">{logo}<div class="nm"><span class="site">{e(ev["site"])}</span> {e(ev["opponent"])}</div></div>
      <div class="line">{foot}</div>
    </div>"""


def render_strip(events, recent_n=2, next_n=4):
    """A wide, short board that fits Populi's 146px Feed excerpt clip.

    Six panels: the most recent finished games, then the next fixtures. Wide
    enough to cross sports rather than reading as a single-sport ticker.
    """
    picked = select(events, datetime.now(TZ).date(), recent_n, next_n)

    stamp = datetime.now(TZ).strftime("%b %-d, %-I:%M %p")
    body = "\n".join(_tile_html(ev, len(picked)) for ev in picked)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MCC Thunder Scoreboard</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kanit:wght@400;600;700&display=swap" rel="stylesheet">
<style>{strip_css(len(picked))}</style>
</head>
<body>
<div class="wrap">
  <header>
    <img class="brand" src="{BRAND_LOGO.as_posix()}" alt="MCC Thunder">
    <span class="tag">Scoreboard</span>
    <span class="stamp">Updated {stamp}</span>
  </header>
  <div class="tiles">
{body}
  </div>
</div>
</body>
</html>
"""


def render(events, source_url=SITE_URL, refresh_seconds=900):
    recent = [ev for ev in events if ev["played"]][:4]
    upcoming = [ev for ev in events if not ev["played"]][:4]
    stamp = datetime.now(TZ).strftime("%b %-d, %-I:%M %p")

    sections = []
    if recent:
        sections.append(
            '  <div class="section-label">Latest Results</div>\n'
            + "\n".join(_row_html(ev) for ev in recent)
        )
    if upcoming:
        sections.append(
            '  <div class="section-label">Up Next</div>\n'
            + "\n".join(_row_html(ev) for ev in upcoming)
        )
    body = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{refresh_seconds}">
<title>MCC Thunder Scoreboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kanit:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    font-family: Kanit, "Helvetica Neue", Arial, sans-serif;
    background: {NAVY};
    color: {WHITE};
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ padding: 0 0 10px; }}

  header {{
    display: flex; align-items: center; gap: 12px;
    background: {WHITE}; padding: 7px 14px;
    border-bottom: 3px solid {LIGHT};
    margin-bottom: 12px;
  }}
  header .brand {{ height: 40px; width: auto; display: block; }}
  header .tag {{
    font-size: 11px; font-weight: 600; letter-spacing: .16em;
    color: {NAVY}; text-transform: uppercase;
    padding-left: 12px; border-left: 1px solid {GRAY};
  }}
  header .stamp {{
    margin-left: auto; font-size: 10px; white-space: nowrap;
    color: rgba(0, 32, 82, .55);
  }}
  .section-body {{ padding: 0 10px; }}

  .section-label {{
    font-size: 10px; letter-spacing: .16em; text-transform: uppercase;
    color: {LIGHT}; margin: 12px 4px 6px;
  }}
  .section-label:first-child {{ margin-top: 0; }}

  .row {{
    display: flex; align-items: center; gap: 12px;
    background: {SURFACE};
    border-left: 3px solid {LIGHT};
    padding: 8px 12px;
    margin-bottom: 4px;
    text-decoration: none; color: inherit;
    transition: background .12s ease;
  }}
  a.row:hover {{ background: {HOVER}; }}

  .date {{
    flex: 0 0 44px; text-align: center; line-height: 1.05;
    border-right: 1px solid rgba(255,255,255,.14); padding-right: 8px;
  }}
  .date .dow {{ display: block; font-size: 9px; letter-spacing: .1em; color: {LIGHT}; }}
  .date .mon {{ display: block; font-size: 9px; letter-spacing: .1em; color: {LIGHT}; }}
  .date .num {{ display: block; font-size: 20px; font-weight: 700; }}

  .logo {{ flex: 0 0 34px; width: 34px; height: 34px; object-fit: contain; }}
  .logo-blank {{ display: block; }}

  .meta {{ flex: 1 1 auto; min-width: 0; }}
  .meta .sport {{ font-size: 10px; letter-spacing: .1em; color: {LIGHT}; text-transform: uppercase; }}
  .meta .opp {{
    font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: .01em;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .meta .opp .site {{ color: {LIGHT}; font-weight: 400; }}
  .meta .city {{ font-size: 10px; color: {GRAY}; text-transform: uppercase; }}

  .outcome {{ flex: 0 0 auto; text-align: right; white-space: nowrap; }}
  .badge {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 19px; height: 19px; margin-right: 6px; border-radius: 2px;
    font-size: 12px; font-weight: 700; line-height: 1; vertical-align: -3px;
  }}
  .badge.win {{ background: {WIN_BG}; color: {WIN_FG}; }}
  .badge.loss {{ background: {LOSS_BG}; color: {LOSS_FG}; }}
  .badge.tie {{ background: {TIE_BG}; color: {TIE_FG}; }}
  .score {{ font-size: 15px; font-weight: 600; }}
  .upcoming {{ font-size: 13px; font-weight: 600; color: {WHITE}; }}

  footer {{ margin-top: 10px; text-align: right; }}
  footer a {{ font-size: 11px; color: {LIGHT}; text-decoration: none; letter-spacing: .04em; }}
  footer a:hover {{ text-decoration: underline; }}

  @media (max-width: 460px) {{
    .meta .city {{ display: none; }}
    .row {{ gap: 8px; padding: 7px 9px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <img class="brand" src="{BRAND_LOGO.as_posix()}" alt="MCC Thunder">
    <span class="tag">Scoreboard</span>
    <span class="stamp">Updated {stamp}</span>
  </header>
  <div class="section-body">
{body}
  <footer><a href="{html.escape(source_url)}" target="_blank" rel="noopener">Full schedule at mccthunder.com &rsaquo;</a></footer>
  </div>
</div>
</body>
</html>
"""


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def shoot(html_path, png_path, width=760):
    """Render the page to a PNG with headless Chromium."""
    from playwright.sync_api import sync_playwright

    uri = pathlib.Path(html_path).resolve().as_uri()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": 400}, device_scale_factor=2
        )
        page.goto(uri)
        page.wait_for_timeout(2500)  # let webfonts and opponent logos land
        page.locator(".wrap").screenshot(path=png_path)
        browser.close()


def upload(local, s3_uri, content_type, max_age):
    subprocess.run(
        [
            "aws", "s3", "cp", local, s3_uri,
            "--content-type", content_type,
            "--cache-control", f"public, max-age={max_age}, must-revalidate",
        ],
        check=True,
    )
    print(f"uploaded {local} -> {s3_uri}")


def main():
    ap = argparse.ArgumentParser(description="Build the MCC Thunder scorebug.")
    ap.add_argument("--out", default="index.html", help="output HTML path")
    ap.add_argument("--png", help="render the strip PNG (what the Home feed shows)")
    ap.add_argument("--png-full", help="render the full board PNG (behind 'See more')")
    ap.add_argument("--s3-png-full", help="s3://bucket/key for the full board PNG")
    ap.add_argument("--width", type=int, default=760, help="PNG render width in px")
    ap.add_argument(
        "--layout",
        choices=("strip", "list"),
        default="strip",
        help="strip = wide/short, fits Populi's 146px Feed clip (default); "
             "list = tall vertical board for the full article view",
    )
    ap.add_argument("--recent", type=int, default=2, help="played games in the strip")
    ap.add_argument("--next", type=int, default=4, dest="next_n",
                    help="upcoming games in the strip")
    ap.add_argument("--from-file", help="parse a saved HTML file instead of fetching")
    ap.add_argument("--json", action="store_true", help="print parsed events and exit")
    ap.add_argument("--s3", help="s3://bucket/key for the HTML (optional)")
    ap.add_argument("--s3-png", help="s3://bucket/key for the PNG (this is the one Populi uses)")
    args = ap.parse_args()

    if args.from_file:
        with open(args.from_file, encoding="utf-8") as fh:
            markup = fh.read()
    else:
        markup = fetch()

    events = apply_overrides(parse(markup))
    today = datetime.now(TZ).date()
    for ev in events:
        ev["dt"] = event_date(ev, today)

    if args.json:
        json.dump(events, sys.stdout, indent=2)
        print()
        return

    if args.layout == "strip":
        page = render_strip(events, recent_n=args.recent, next_n=args.next_n)
    else:
        page = render(events)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {args.out} ({len(page)} bytes, {len(events)} events)")

    if args.png:
        shoot(args.out, args.png, width=args.width)
        print(f"wrote {args.png}")

    # The full board: clipped out of the Home feed, revealed by "... See more".
    if args.png_full:
        full_html = args.out + ".full.html"
        with open(full_html, "w", encoding="utf-8") as fh:
            fh.write(render(events))
        shoot(full_html, args.png_full, width=args.width)
        print(f"wrote {args.png_full}")

    # Short max-age plus must-revalidate: viewers pick up new scores within the
    # minute without refetching an unchanged image on every dashboard load.
    if args.s3:
        upload(args.out, args.s3, "text/html; charset=utf-8", 300)
    if args.s3_png:
        if not args.png:
            sys.exit("--s3-png requires --png")
        upload(args.png, args.s3_png, "image/png", 60)
    if args.s3_png_full:
        if not args.png_full:
            sys.exit("--s3-png-full requires --png-full")
        upload(args.png_full, args.s3_png_full, "image/png", 60)


if __name__ == "__main__":
    main()
