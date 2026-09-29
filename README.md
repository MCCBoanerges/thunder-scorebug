# MCC Thunder scorebug for the Populi homepage

An auto-updating athletics scorebug on the Populi Home dashboard. Scraped from
mccthunder.com, rendered to PNGs by a GitHub Actions job every 15 minutes,
published to GitHub Pages, and hot-linked from one News post that is written once
and never edited again.

## What was verified in Populi (2026-08-31, mccks.populiweb.com)

**Test 1, what survives a save.** Created an unpublished News item and inspected
the stored HTML:

| Attempted | Result |
| --- | --- |
| `<iframe src="…s3.amazonaws.com/…">` | **`src` stripped.** The tag survives, gutted and empty. |
| `<iframe src="https://mccthunder.com/">` | Same, `src` stripped. |
| `<img src="https://mccthunder.com/…/dallch.png">` | **Survives intact and renders.** |
| `<img>` inside `<a href>` to an external site | **Survives**, Populi adds `rel="noreferrer noopener"`. |

The iframe whitelist Populi documents for lessons and tests does not extend to
News. News strips iframe sources outright. External images pass through with no
domain restriction at all.

That is the whole design. A hot-linked PNG at a fixed URL is functionally a live
widget: the cron job overwrites the image, and every dashboard load fetches
whatever is currently there.

**Test 2, how Home renders it.** Published the item scoped to the Account Admin
role only, then looked at Home:

- News items land in **The Feed** on the Home dashboard, external image rendered
  inline. The `width` attribute is honored exactly.
- The feed column is roughly 1100px wide, so a 760px image fits comfortably.
- **The excerpt is clipped at 146px.** Populi wraps the body in
  `div.truncation_block.newsitem-content` with `max-height: 146px; overflow:
  hidden` and appends "... See more".

That clip is the real design constraint, and it is why the board is a wide strip
rather than the tall list I built first. Anything past 146px is invisible unless a
person clicks through.

The test item was set back to unpublished afterward. It is sitting in Manage News
titled "Thunder Scoreboard (visibility test, Account Admin only)", visible to
nobody. Delete it when convenient.

## The two-image trick

The post carries two hot-linked images stacked:

1. `scorebug.png`, the 760x145 strip: six panels, the two most recent results and
   the next four fixtures. Fits inside the 146px clip, so this is what everyone
   sees on Home without clicking anything. Six is wide enough to carry a whole
   busy day, and to cross sports rather than reading as a single-sport ticker.

   Change the split with `--recent` and `--next`. The layout sizes itself to the
   count: five panels get 32px logos, 11px names and full sport labels; six drop
   to 26px logos, 10px names, a fourth name line, and abbreviated sport labels
   ("W CROSS COUNTRY"), because a six-wide tile is only about 118px. Seven does
   not fit.
2. `scoreboard.png`, the full 760x492 board with more games and the results and
   upcoming split out. Clipped out of the feed, revealed by "... See more".

Both refresh on the same cron run. Put the strip first; the clip budget is spent
top-down and anything above the image eats into it, so no intro paragraph.

## Files

| File | Purpose |
| --- | --- |
| `scrape_mcc.py` | Scrapes, renders both layouts, optionally uploads |
| `make_fixture.py` | Regenerates `fixture.html` for offline parser testing |
| `fixture.html` | Homepage markup shape with real data from 2026-08-31 |
| `logos/` | Opponent marks plus the Thunder banner; overrides keyed by the site's filename |
| `overrides.json` | Scores you know before the athletics site posts them |
| `.github/workflows/scorebug.yml` | The 15-minute render-and-publish job |
| `web/index.html` | Landing page for the Pages site, shows both boards |
| `requirements.txt` | requests, beautifulsoup4, playwright |
| `scorebug.png` | Sample strip, the thing the Home feed displays |
| `scoreboard.png` | Sample full board, behind "See more" |

## How the data works

The athletics site is Drupal 8 on PressboxU and server-renders everything. No JSON
API, no XHR endpoint, so the scorebug parses rendered rows.

The source is **the composite calendar at `/calendar`**, not the homepage. The
homepage block looks like the obvious feed and uses identical row markup, but it
is a rolling six-row window: results drop off it within a day or two, so it
cannot reliably answer "what were the last two games". The calendar carries the
whole season. The parser accepts either.

Selection is **by date, not by feed position**. That matters because a cross
country meet never gets a win/loss posted, so going by "has a result" alone
leaves it looking upcoming forever and clogging the board weeks after it was run.
Anything dated before today is out of the fixtures list regardless.

Consecutive days of the same event collapse into one panel. Golf plays the same
course Monday and Tuesday and the site lists each day separately, which would
otherwise spend two of six panels on one tournament; it now renders as a single
`SEP 14-15` panel.

```
div.view-event-schedule
  div.views-row
    span.day / span.month / span.date    date block
    div.logo > img[src]                  opponent logo
    div.site                             "VS." or "AT"
    div.sport / div.opponent / div.city  event identity
    div.result                           "W, 3-2"   (played)
    div.time                             "5:00 PM"  (upcoming)
    div.live-video > a[href]             YouTube stream link
```

If PressboxU restyles the site this is what breaks, and the script raises a clear
error rather than silently publishing an empty board.

## Deployment

Populi puts no domain restriction on images, so the PNGs can be served from
anywhere reachable over HTTPS. This repo is set up to run on GitHub Actions and
publish to GitHub Pages: nothing on the MCC estate to patch, no storage account,
no bill, and no server that can quietly stop working without anyone noticing.

### 1. Create the repo

Push this directory to a **public** GitHub repo under the MCC organization.
Public matters for two reasons: Actions minutes are unlimited on public repos
(96 runs a day would otherwise eat the free private allowance), and Pages serves
the images without authentication, which is what Populi needs. Nothing here is
sensitive; it is public athletics data rendered into a picture.

### 2. Turn on Pages

Settings > Pages > Build and deployment > Source: **GitHub Actions**.

Do not pick "Deploy from a branch". The workflow publishes the rendered images
as a Pages artifact, so nothing is ever committed back to the repo and the
history stays clean.

### 3. Run it once

Actions > Scorebug > Run workflow. It takes about ninety seconds, most of that
installing Chromium. When it finishes, the images are live at:

```
https://<org>.github.io/<repo>/scorebug.png
https://<org>.github.io/<repo>/scoreboard.png
```

Visiting the root of that URL shows both boards on one page, which is a
convenient thing to send people who ask where the numbers come from.

After that it runs itself every 15 minutes on the schedule in
`.github/workflows/scorebug.yml`, and also on any push that touches the script,
the logos, or the workflow.

### 4. The News post (one time)

Communications > News > Add News. Open the `<>` source view and paste, with your
own Pages URLs substituted:

```html
<p><a href="https://mccthunder.com/" target="_blank"><img
  src="https://<org>.github.io/<repo>/scorebug.png"
  alt="MCC Thunder scoreboard: latest results and upcoming games"
  width="760" /></a></p>
<p><a href="https://mccthunder.com/" target="_blank"><img
  src="https://<org>.github.io/<repo>/scoreboard.png"
  alt="Full Thunder scoreboard"
  width="760" /></a></p>
```

Title it "Thunder Scoreboard", set **Featured: Yes**, leave visibility open.
Then never touch it again. The URLs are stable; the contents change under them.

## Running it anywhere else

Nothing about the script is tied to GitHub. It takes `--s3-png` and
`--s3-png-full` and shells out to the AWS CLI, and writing to Azure Blob or a
local web root is a one-line change to `upload()`. On a server with cron:

```cron
*/15 * * * * cd /opt/mcc-scorebug && /usr/bin/python3 scrape_mcc.py --png scorebug.png --png-full scoreboard.png --s3-png s3://BUCKET/scorebug.png --s3-png-full s3://BUCKET/scoreboard.png >> /var/log/mcc-scorebug.log 2>&1
```

Uploads carry `Cache-Control: public, max-age=60, must-revalidate`. Wherever you
host, keep the cache short or viewers will sit on a stale board.

## Getting ahead of the site

The athletics site can lag a final by hours, and the homepage block sometimes
never shows an in-progress game at all. `overrides.json` lets a known score go up
immediately:

```json
[
  {"month": "SEP", "date": "5", "opponent": "BETHANY", "result": "L, 0-3",
   "note": "why this is here"}
]
```

Matching is month plus date plus a case-insensitive substring of the opponent, so
`BETHANY` matches `BETHANY COLLEGE (KAN.)`. Results are written the way the site
writes them, MCC's score first: `W, 3-0`, `L, 0-3`.

The important rule: **an override only applies to a game the site still shows as
unplayed.** The moment the site publishes its own result, the site wins and the
entry goes inert. A stale override can never contradict the source of truth, so
forgetting to clean one up costs nothing. Tidy the file out when convenient.

Commit the edit and the workflow's push trigger rebuilds the board within a
minute or two, rather than waiting for the next quarter-hour tick.

## Operating it

**Freshness.** The board refreshes every 15 minutes, and GitHub Pages puts its
own 10-minute cache in front of the images, which it does not let you override.
Worst case a score is about 25 minutes behind the athletics site. Fine for a
dashboard nobody is watching live; if you want it tighter, drop the cron to
`*/5` and accept that Pages still caches for 10.

**Scheduled cron is approximate.** GitHub runs scheduled workflows on a
best-effort basis and they can drift 5 to 15 minutes when the platform is busy.
Occasionally a run is skipped entirely. This is a scoreboard, so that is fine,
but do not build anything time-critical on this schedule.

**Failure alerts come free.** GitHub emails the repo owner when a scheduled
workflow fails. The workflow also checks that both PNGs actually rendered and
are a plausible size, and fails loudly rather than publishing a blank board. A
scoreboard that is quietly wrong is worse than one that is visibly broken.

**Watch for the 60-day sleep.** GitHub disables scheduled workflows in repos
with no activity for 60 days. It emails first. If the board freezes over a long
off-season, that is the likely cause; re-enable it from the Actions tab, or push
any commit.

**When it breaks, it will be the athletics site.** The parser depends on the DOM
contract above. If PressboxU restyles, the run fails with a clear message
pointing at `div.view-event-schedule` rather than publishing an empty board.

## Brand

Everything on the board is one of the four school colors, or one of them tinted
with white or black over the navy, so no fifth hue enters the design.

| Role | Color |
| --- | --- |
| Ground, badge text | Primary `#002052` |
| Rules, sport labels, "VS.", section headings | Tertiary `#A3BCDB` |
| Muted text, upcoming-game accents | Alternate `#ADAFB1` |
| Opponent names, scores, win square | White `#FFFFFF` |
| Loss square ground | Black `#000000` |

Two decisions worth flagging, either of which is easy to reverse:

**The header band is white.** The Thunder banner mark is a navy shield, so on the
primary navy it would sink into the background. Giving it a white ground is the
only way to use the logo as supplied without recoloring it, and it reads like a
broadcast lower-third. The alternative is a navy header with the logo sitting on a
small white plate, which is quieter but fussier.

**Results are squares, not green and red pills.** A win is a white square with a
navy W; a loss is a black square with a tertiary L. Green and red are not school
colors, and the letter already carries the meaning. The pairs live at the top of
`scrape_mcc.py` as `WIN_BG` / `WIN_FG` and `LOSS_BG` / `LOSS_FG` if you want to
change them; `TIE_BG` / `TIE_FG` covers the rare tie.

The banner mark lives at `logos/mcc-thunder.png`, trimmed of its white margin.
Replace that file to change the logo; the header sizes to whatever you put there.

## Opponent logos

Every mark on mccthunder.com is exactly **70x70** (one outlier, cbusai, is
150x150). Copy-pasting them off the page, as you did, gets the original file byte
for byte, so there is no better version hiding behind the one you see. That is the
resolution the athletics site has.

70px is enough for the strip because the logo slot is **32px**, which is 64 device
pixels at the 2x render. Going bigger than about 35px starts upscaling and the
marks go soft, which is why the tile is laid out around that size rather than a
larger one.

If you do want a sharper mark for a particular opponent, drop it in `logos/` named
after the athletics site's own filename and the renderer prefers it:

```
logos/sterlc.png     overrides https://mccthunder.com/…/images/teams/sterlc.png
```

Any size works; it gets scaled down to 32px. The four you sent are already in
there as examples. Good places to look for better source art are the opponent's
own athletics site and the conference site at mcccsports.com.

One naming quirk worth knowing: the file the site serves for Randall University is
called `hillsd.png`, but it does contain Randall's actual mark. Confusing filename,
correct logo. Nothing to fix.

## Notes

- Logos are baked into the PNGs at render time, so Populi viewers never hit the
  athletics site.
- PNGs render at 2x for retina and are displayed at 760 CSS px.
- Dark navy on their own background, so they read correctly in both Populi themes.
- `--layout list` and the generated HTML page are still there. If Populi ever
  allows iframe sources in News, switch to the page and the rows become clickable
  links to the game streams.
- The 146px clip is a Populi CSS value, not a documented contract. If a Populi
  update changes it, the strip is what needs re-measuring.
