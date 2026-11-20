# CLAUDE.md

Two independent Arabic-RTL systems for an Iraqi electronics retailer (~600 display stands, ~300 staff).

## `display-cleaning/` — dust-cleaning compliance app (Firebase)
- Single `index.html`; Firestore + Cloud Functions (`functions/`), rules in `firestore.rules`.
- Deployed automatically to Firebase Hosting on every merge to `main` (`.github/workflows/deploy.yml`, see `SETUP.md`). The deploy also copies `display-guard/haris.html` to `/haris.html` and rewrites `/api/judge` to the `judgeEvent` function.
- Technical notes: `display-cleaning/SUMMARY.md`.

## `display-guard/` — حارس العارضات (camera-based stand monitor)
Read `display-guard/PROJECT_SUMMARY.md` first (history, algorithms, thresholds, field-test lessons, roadmap).
- Edit `src/page.html` and `src/detector.js`, then `python3 build.py` → `haris.html` (single file, no bundler). Commit the rebuilt `haris.html`.
- Tests (from `display-guard/`), all must pass after any detector/engine change:
  - `node tests/unit_detector.js`
  - `python3 tests/make_videos.py` (once; needs numpy, pillow; output in `tests/out/`, git-ignored)
  - `CHROME=/usr/bin/google-chrome python3 tests/run_scenarios.py` (Python playwright; ~20 min, real time)
  - `node tests/judge_server.js` (server judge with a fake Claude client) and `node tests/judge_client.js` (page reaction to verdicts, mocked endpoint) — no API cost
- Camera needs HTTPS (or file:// / localhost).

### Hard rules
- No manual product entry; detection is change-based, the baseline rebases per zone after every decision.
- No per-frame cloud AI calls (cost). The on-device engine (JS math + optional MediaPipe) is the 24/7 trigger. Per-event cloud judging is allowed (user-approved): `functions/judge.js` (`judgeEvent`, Claude Opus 5.5 default) behind `GUARD_KEY`; the page degrades gracefully without it.
- Removal ≠ alarm: pending → returned / sold / cleaning-extended → incident after grace (night = immediate).
- Never rebase the whole frame for exposure/white-balance changes alone.
- Every new field bug: reproduce as a y4m scenario in `make_videos.py` + `run_scenarios.py` first, then fix.

## `archive/`
- `nvr-python/`: Hikvision ISAPI version, older detector, shelved (also supplies `demo.py` for the `live` test video).
- `shelf-prototype/`: first prototype, reference only.
