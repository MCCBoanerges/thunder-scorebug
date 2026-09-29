# MCC Thunder Scorebug — project handoff

Paste this into a new conversation to pick the project up. It carries the
decisions and the hard-won facts; `README.md` in the same folder carries the
operating detail.

**Status as of 2026-09-29:** the board works and is running **by hand**. Every
few days Josh renders a fresh PNG, uploads it into a Populi News post, and pastes
the `<img>` tag back to have `width="760"` added. The automation that ends this
loop is written and sitting in the repo unused. The sample PNGs in the folder are
from **Sep 14** and are stale.

---

## 1. What this is

An athletics scoreboard on the Manhattan Christian College **Populi** home
dashboard (`mccks.populiweb.com`), fed from the athletics site
**mccthunder.com**. Josh Jones is Director of IT and Operations at MCC.

Populi's Home dashboard has a fixed layout and no widget system, so the board is
delivered as a **hot-linked PNG inside a Featured News post**. Regenerate the
image at a stable URL and every dashboard load shows current scores, without the
post ever being edited again.

---

## 2. Populi facts, verified by testing

These were established by creating a real News item and inspecting what survived.
Do not re-derive them; they are not in Populi's documentation.

| Behavior | Finding |
| --- | --- |
| `<iframe src="...">` in a News post | **`src` is stripped on save.** The tag survives, gutted. True for every domain tried, including AWS. |
| The documented iframe whitelist | Applies to **lessons and tests only**, not News. |
| `<img src="https://any-domain/...">` | **Survives intact.** No domain restriction at all. This is why the design is an image. |
| `<img>` wrapped in `<a href>` | Survives; Populi adds `rel="noreferrer noopener"`. |
| Where News appears | In **The Feed** on Home, image rendered inline. The `width` attribute is honored exactly. |
| Feed excerpt height | **Clipped at 146px.** `div.truncation_block.newsitem-content` has `max-height: 146px; overflow: hidden`, then "... See more". **This is the governing design constraint.** |
| Feed column width | ~1100px on a wide display. A 760px image fits with room. |
| Freshly uploaded images | Get a **temporary presigned S3 URL** on `tmp.populi.co` that expires in minutes. Populi rewrites it to a permanent `mccks.populiweb.com/router/files/...` URL on save. The `data-key` attribute is what Populi uses to finalize the file. |
| Editor location | Communications > News > Add News. The `<>` button opens an HTML source view. |
| Publication controls | Publish Yes/No, Featured Yes/No, and Visibility by campus and by Role. **Publish: No** is a safe way to test without anyone seeing it; a narrow role such as Account Admin scopes a published test. |

**Leftover:** an unpublished item titled "Thunder Scoreboard (visibility test,
Account Admin only)" is still in Manage News. Harmless, delete when convenient.

---

## 3. Design constraints that drove every decision

- **146px is a hard ceiling.** The strip renders at 760x145, one pixel under.
  There is no room to take.
- **The image must carry `width="760"`.** Without it the image stretches to the
  feed column (~1446px) and becomes ~276px tall, which the clip cuts in half.
  Every fresh Populi upload comes back **without** a width attribute, so it has
  to be re-added by hand each time. This is the single most repeated task in the
  project and it disappears the moment the `src` points at a stable URL.
- **Six panels is the maximum.** At six, each tile is ~118px. The layout sizes
  itself: five panels get 32px logos, 11px names, full sport labels; six drop to
  26px logos, 10px names, a fourth name line, and abbreviated sport labels
  ("W CROSS COUNTRY", "M/W CROSS COUNTRY"). Seven does not fit.
- **Two images, stacked.** The 145px strip is what everyone sees. A taller full
  board sits under it, clipped out of the feed, revealed by "See more".

---

## 4. Data source and its traps

The athletics site is **Drupal 8 on PressboxU**. No JSON API, no XHR endpoint,
everything server-rendered. Two traps cost real time:

1. **Do not scrape the homepage block.** `div.view-event-schedule` on the
   homepage looks like the obvious feed, but it is a **rolling six-row window**.
   Results drop off it within a day or two, so it cannot answer "the last two
   games". The source is **`https://mccthunder.com/calendar`**, which carries the
   whole season in identical row markup. The parser accepts either.
2. **Select by date, not by "has a result".** Cross country meets never get a
   win/loss posted. Under a result-only test they look like upcoming fixtures
   forever and clog the board weeks after they were run. Anything dated before
   today is excluded from fixtures regardless.

Row markup:

```
div.views-row
  span.day / span.month / span.date    date block (no year — inferred)
  div.logo > img[src]                  opponent logo
  div.site                             "VS." or "AT"
  div.sport / div.opponent / div.city  event identity
  div.result                           "W, 3-2" (played)
  div.time                             "5:00 PM" (upcoming; "12:00 AM" means TBA)
  div.live-video > a[href]             YouTube stream link
```

Other quirks: opponent logos are all **70x70** (one is 150), which is exactly
enough for the 32px slot at 2x and no more. The file served for Randall
University is named `hillsd.png` but contains Randall's correct mark. Sport can
hold two values at once ("MENS CROSS COUNTRY, WOMENS CROSS COUNTRY").

---

## 5. The code

`scrape_mcc.py` is the whole thing. Notable pieces:

- `parse()` — reads rows from either the calendar or the homepage block.
- `apply_overrides()` — reads `overrides.json`, which lets a known final go up
  before the athletics site posts it. **The safety rule: an override only applies
  to a game the site still shows as unplayed.** Once the site publishes its own
  result the site wins and the entry goes inert, so a stale override can never
  contradict the source. This has already proven itself twice.
- `event_date()` — the site prints no year; picks the reading nearest today so a
  season crossing the new year resolves correctly.
- `merge_multiday()` — collapses consecutive same-sport, same-opponent,
  same-venue fixtures into one panel with a date range ("SEP 14-15"). Built for
  two-day golf; the NCCAA regional will use it too.
- `select()` — most recent finished games, then next fixtures, by date, with
  backfill when one side is short.
- `render_strip()` / `render()` — the 145px strip and the full board.
- `strip_css(tiles)` — the layout metrics that change between five and six panels.

Brand palette (from Josh): primary `#002052`, alternate `#ADAFB1`, tertiary
`#A3BCDB`, white `#FFFFFF`. The header band is **white** because the Thunder
shield is navy and would sink into the primary color. Result chips are a white
square with a navy W and a black square with a tertiary L; green and red were
rejected as off-brand.

Files: `scrape_mcc.py`, `overrides.json`, `logos/` (opponent marks plus
`mcc-thunder.png` banner), `make_fixture.py` + `fixture.html` for offline parser
testing, `.github/workflows/scorebug.yml`, `web/index.html`, `requirements.txt`,
`README.md`.

---

## 6. The automation, built but not deployed

This is the open item and it is entirely on Josh's side. Roughly twenty minutes:

1. Push the folder to a **public** GitHub repo under the MCC org. Public matters:
   unlimited Actions minutes, and Pages serves images unauthenticated.
2. Settings > Pages > Source: **GitHub Actions** (not "deploy from a branch").
3. Actions > Scorebug > Run workflow. Images land at
   `https://<org>.github.io/<repo>/scorebug.png` and `/scoreboard.png`.
4. One News post pointing at those URLs, Featured: Yes. Never edited again.

The workflow runs every 15 minutes, verifies both PNGs rendered at a plausible
size before publishing (so a scrape failure fails loudly instead of putting a
blank board in front of the college), and GitHub emails on failure.

Known limits: Pages caches images ~10 minutes and won't let you override it, so
worst case a score is ~25 minutes behind. Scheduled Actions drift 5-15 minutes.
GitHub disables scheduled workflows after 60 days of repo inactivity, with an
email first.

---

## 7. Open questions

- **Deploy the automation.** Everything else is downstream of this.
- Sport labels abbreviate at six panels. Josh has not objected but has not
  confirmed he likes it either.
- Higher-resolution opponent logos: `logos/<code>.png` overrides the site's 70px
  mark at any size, if better source art ever turns up.

---

## 8. Working notes

Josh iterates fast and in small steps, usually by pasting a screenshot of the
current athletics site or the Populi source view. Useful habits from this
project:

- **Check the live site before rendering.** He often pastes a screenshot, but
  scraping `mccthunder.com/calendar` in the browser gets exact strings, logo
  filenames and times. Times have moved by an hour without announcement.
- **Verify in Populi rather than reasoning about it.** Twice, measuring the live
  DOM overturned a confident theory: the "bottom is cut off" complaint turned out
  to be nothing being clipped at all, just a tile edge with too little contrast.
- **When he pastes an `<img>` tag, he wants it back with `width="760"` added**
  and nothing else changed. Check the `Expires=` timestamp in the URL and tell
  him how long he has.
- No em dashes in replies.
