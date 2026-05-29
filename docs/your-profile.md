# Your profile (`config/profile.yaml`)

Fill these in right after `./scripts/onboard.sh` (or `onboard.ps1` on Windows) copies `config/profile.example.yaml` to `config/profile.yaml`. This file is **gitignored** — it holds your geography, pay floors, stack keywords, and scrape settings.

Validate after edits:

```bash
python3 -c "from jobspy.profile_loader import get_profile; print(get_profile()['_meta']['path'])"
```

Override path for tests: `export QA_JOB_PROFILE=/path/to/profile.yaml`

---

## Onboarding fields

### `owner`

**What:** Display name for scrape logs and triage output — not sent to job boards.

**Example:** `owner: jordan-qa`

**Why:** So you can tell your runs apart in CSV filenames and console output.

---

### `remote_preference`

**What:** How strictly the pipeline filters work arrangement (US-focused). One of:

| Value | Behavior |
|-------|----------|
| `fully_remote` | Keep rows with clear US-remote language in the JD |
| `hybrid_home_metro` | US-remote **or** hybrid/onsite only when JD + location match your `home_metro.place_names` |
| `any_us_remote` | Broadest US filter; still blocks international location columns |

**Example:** `remote_preference: hybrid_home_metro` if you would commute locally but want full remote too.

**Why:** Stops the scraper from surfacing onsite-only roles outside your commute zone.

---

### `home_metro.name`, `zip_anchor`, `place_names`

**What:**

- **`name`** — Display label for logs only (e.g. `Portland metro`). Not used for matching.
- **`zip_anchor`** — Your home-area US ZIP (5 digits). Anchor for hybrid commute; kept for reference and future radius logic.
- **`place_names`** — Lowercase city/suburb strings matched as **substrings** in job `location` and JD text.

**Example:**

```yaml
home_metro:
  name: Portland metro
  zip_anchor: "97209"
  place_names:
    - portland
    - beaverton
    - hillsboro
```

**Why:** Hybrid-in-your-area logic depends on `place_names`, not `name`. Add suburbs you would actually commute to.

---

### `silent_office_hubs`

**What:** US office cities that often appear in the **location column** when the JD says nothing about remote. In `hybrid_home_metro` mode, rows naming one of these hubs (without "Remote" and without matching your `place_names`) are dropped.

**Example:** Keep defaults like `seattle`, `san francisco`, `new york`; **remove your own metro** (e.g. `portland`) if local listings get filtered incorrectly.

**Why:** Filters misleading location columns — e.g. LinkedIn shows "Seattle, WA" but the JD never mentions remote.

**Skip for now?** You can leave bundled defaults and tune after your first triage run. For hybrid rules and ILS interaction, see [ils-matrix.md](ils-matrix.md).

---

### `comp.*` — pay floors

All values are **USD, annualized** unless noted.

| Key | What it does |
|-----|--------------|
| `min_ceiling_usd` | Scraper L1 pass if posted **max** ≥ this |
| `min_floor_usd` | Scraper L1 pass if posted **min** ≥ this |
| `hourly_annual_floor_usd` | Hourly postings annualized at 2080 hrs/yr; must meet this |
| `gate2_floor_usd` | Minimum salary for the **`gate2_at_145k`** CSV column (legacy name — floor comes from this key) |

The `gate2_at_145k` column is **not** a job-fit score. It labels JD-extracted comp vs your floor: `PASS`, `MARGINAL`, `FAIL`, or `UNKNOWN`.

**Example (senior IC QA):**

```yaml
comp:
  min_ceiling_usd: 140000
  min_floor_usd: 120000
  hourly_annual_floor_usd: 120000
  gate2_floor_usd: 150000
```

**Why:** Sets the pay bar before you spend time on postings below your range.

---

### `prescreen.stack_keywords`

**What:** Words and phrases counted in the JD to populate the `stack_hits` column.

**Example:**

```yaml
stack_keywords:
  - playwright
  - python
  - pytest
  - typescript
  - github actions
  - rest api
```

**Why:** Surfaces rows whose JD mentions tools you actually use. Greenhouse (`GH`) track rows often have no description → `stack_hits` stays 0; open the URL manually.

---

### `prescreen.priority` (defaults usually fine)

**What:** Regex year caps that set the `priority` column to `HIGH`, `MOD`, `LOW`, or `?`.

| Key | Default | Effect |
|-----|---------|--------|
| `max_years_high` | 7 | Title suggests ≤ this → `HIGH` |
| `max_years_mod` | 8 | Between HIGH and LOW caps → `MOD` |
| `max_years_low` | 8 | Higher year bar → `LOW` |

**Why:** Rough sort flag for manual review — **not** a hire score or ILS ranking. Tune only if priority tags feel systematically wrong.

---

### `paths.skip_companies`

**What:** Path to a blocklist text file — one company slug per line. Onboarding copies `config/skip_companies.txt.example` to `applications/skip_companies.txt`.

**Example:** Start from the copied file; add employers as you learn you do not want them:

```
# one slug per line, lowercase
some-corp
another-employer
```

**Why:** Keeps known bad fits out of triage. Grows over time — no need to pre-fill everything on day one.

---

### `tracks.enable`

**What:** Which scrape **channels** run in `jobspy/run_search_locally.py`.

| Track | Description |
|-------|-------------|
| **A** | General QA/SDET Indeed + LinkedIn style queries |
| **B** | Automation-focused query set |
| **C** | Contract / staff-aug patterns |
| **G** | Google Jobs |
| **R** | Remotive board |
| **GH** / **L** / **AS** | Greenhouse / Lever / Ashby company lists |

**Recommended for QA onboarding:** `[A]` alone for a minimal first run, or `[A, B]` once A looks healthy. Add ATS boards and contract tracks later.

**Why:** Fewer tracks = faster first scrape and easier debugging.

---

## Later (optional)

After a few scrape + triage cycles, you may want referral tiers (`referrals.status_file`), employers you have verified as truly remote (`verified_remote_employers`), extra manual-review employers (`review_companies`), an applied-companies HTML export (`paths.application_index`), and Interview Likelihood Score tuning (`ils.*`, matrix YAML). Those keys stay in `config/profile.example.yaml` with inline comments — you do not need them for day one.

- [README](../README.md) — quick start, troubleshooting, advanced workflow
- [ils-matrix.md](ils-matrix.md) — ILS formula, referral deltas, hybrid/scoring details
- [installation.md](installation.md) — manual setup and application index contract
