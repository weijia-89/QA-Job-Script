# Your profile (`config/profile.yaml`)

This file is **gitignored** — it holds your geography, pay floors, stack keywords, and scrape settings. Onboarding copies it from `config/profile.example.yaml`; edit it before your first scrape.

Validate after edits:

```bash
python3 -c "from jobspy.profile_loader import get_profile; print(get_profile()['_meta']['path'])"
```

Override path for tests: `export QA_JOB_PROFILE=/path/to/profile.yaml`

---

## When to edit what

| Edit **now** (before first scrape) | Edit **later** (optional) |
|-----------------------------------|---------------------------|
| `owner` | `referrals.status_file` |
| `remote_preference` | `verified_remote_employers` |
| `home_metro` | `review_companies` |
| `silent_office_hubs` (review defaults) | `paths.application_index` |
| `comp.*` floors | `ils.company_overrides_file` |
| `prescreen.stack_keywords` | Extra `tracks` beyond a minimal first run |
| `prescreen.priority` (defaults usually fine) | |
| `tracks.enable` (start with `[A]` if unsure) | |

---

## Field reference

### `owner`

**What it is:** A short label for scrape logs and triage output. Not sent to job boards.

**What to put there:** Any string you recognize — initials, handle, or role tag.

**Example:** `owner: jordan-qa`

**When:** Onboarding.

---

### `remote_preference`

**What it is:** How strictly the pipeline filters work arrangement (US-focused).

**What to put there:** One of:

| Value | Behavior |
|-------|----------|
| `fully_remote` | Keep rows with clear US-remote language in the JD |
| `hybrid_home_metro` | US-remote **or** hybrid/onsite only when JD + location match your `home_metro.place_names` |
| `any_us_remote` | Broadest US filter; still blocks international location columns |

**Example:** `remote_preference: hybrid_home_metro` if you would commute locally but want full remote too.

**When:** Onboarding.

---

### `home_metro.name`

**What it is:** A **display label** for logs and your own reference — city, metro name, or neighborhood phrase. The scraper does **not** match jobs against this string alone.

**What to put there:** Whatever helps you read output, e.g. `Portland metro` or `PDX east side`.

**Example:** `name: Portland metro`

**When:** Onboarding.

**Matching note:** Hybrid-in-your-area logic uses `place_names` (substring match in job `location` + JD text) and `zip_anchor` as your anchor ZIP. Edit `place_names`, not just `name`, when tuning geo filters.

---

### `home_metro.zip_anchor`

**What it is:** Your home-area **US ZIP code** — the geographic anchor for hybrid commute radius. Kept in the profile for reference and future radius logic; current matching is text/heuristic via `place_names`.

**What to put there:** A 5-digit ZIP where you would start a hybrid commute.

**Example:** `zip_anchor: "97209"` (Portland Pearl District)

**When:** Onboarding.

---

### `home_metro.place_names`

**What it is:** A list of lowercase place strings matched as **substrings** against the job `location` column and JD text. Used to decide whether hybrid/onsite roles are in your commute zone.

**What to put there:** Every city, suburb, or neighborhood you would actually commute to for hybrid days. Include common spellings and abbreviations if listings use them.

**Examples:**

```yaml
place_names:
  - portland
  - beaverton
  - hillsboro
  - lake oswego
```

**When:** Onboarding; add more after you see false negatives in triage (`geo_or_work_mode` failures).

---

### `silent_office_hubs`

**What it is:** US office cities that often appear in the **location column** when the JD says nothing about remote. In `hybrid_home_metro` mode, rows whose location names one of these hubs (without "Remote" and without matching your `place_names`) are **dropped**.

**What it is not:** A list of cities you refuse to visit in general. It is a filter for **misleading location columns** — e.g. LinkedIn shows "Seattle, WA" but the JD never mentions remote.

**What to put there:** Lowercase city/region names. The bundled defaults cover major US tech hubs; remove `portland` (or your home hub) if it incorrectly drops local listings.

**Example:** Keep `seattle`, `san francisco`, `new york` in the list; remove your own metro if it appears there.

**When:** Onboarding — skim defaults against where you live.

---

### `comp` — pay floors and JD comp flag

All values are **USD, annualized** unless noted.

| Key | Role |
|-----|------|
| `min_ceiling_usd` | Scraper L1 pass if posted **max** ≥ this |
| `min_floor_usd` | Scraper L1 pass if posted **min** ≥ this |
| `hourly_annual_floor_usd` | Hourly postings annualized at 2080 hrs/yr; must meet this |
| `gate2_floor_usd` | Threshold for the **`gate2_at_145k`** CSV column (legacy column name — see below) |

**`gate2_floor_usd` / `gate2_at_145k`:** This is **not** a job-fit score. It is the **minimum annual salary (USD)** you use to label JD-extracted comp in the CSV:

| CSV value | Meaning (vs your `gate2_floor_usd`) |
|-----------|--------------------------------------|
| `PASS` | Disclosed range meets or exceeds the floor |
| `MARGINAL` | Range straddles the floor |
| `FAIL` | Disclosed max is below the floor |
| `UNKNOWN` | No comp found in JD / structured fields |

The column is still named `gate2_at_145k` for backward compatibility with older spreadsheets; the floor comes from **`gate2_floor_usd`** in your profile (default 145000).

**Example (senior IC QA, US remote/hybrid):**

```yaml
comp:
  min_ceiling_usd: 140000
  min_floor_usd: 120000
  hourly_annual_floor_usd: 120000
  gate2_floor_usd: 150000
```

**When:** Onboarding.

---

### `prescreen.stack_keywords`

**What it is:** Words and phrases counted in the JD to populate the `stack_hits` column.

**What to put there:** Tools, languages, and frameworks you actually use — lowercase, one phrase per line.

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

**When:** Onboarding; refine when you notice relevant JDs with `stack_hits: 0`.

**Note:** Greenhouse (`GH`) track rows often have no description → `stack_hits` stays 0; open the URL manually.

---

### `prescreen.priority`

**What it is:** Regex year caps that set the `priority` column to `HIGH`, `MOD`, `LOW`, or `?`.

**What it means:** A **rough sort flag** for which rows deserve a full manual review session — **not** a hire score, **not** ILS, **not** a ranking of employers.

| Value | Typical use |
|-------|-------------|
| `HIGH` | Title suggests ≤ `max_years_high` years required |
| `MOD` | Between HIGH and LOW caps |
| `LOW` | Higher year bar in title |
| `?` | No JD description — check the posting URL |

**When:** Defaults are usually fine at onboarding; tune if priority tags feel systematically wrong.

---

### `referrals.status_file`

**What it is:** Path to a text file mapping company name substrings to referral warmth. Triage lowers the ILS skip floor for `warm` and `strong` tiers (see [ils-matrix.md](ils-matrix.md#referral-tiers-referralsstatus_file)).

**What to put in the file:** One line per company:

```
company_substring,warm
other corp,strong
```

- **`warm`** — you have a LinkedIn connection or light path in
- **`strong`** — you know someone who can refer you
- Omit a company (or use an **empty file**) → treated as **cold**

Comments start with `#`. Status must be `warm` or `strong` on each data line (`cold` is the default when unlisted).

**Example file:** `applications/referral_status.txt`

**When:** Optional; set **later** when you start tracking referral paths.

---

### `paths.*`

| Key | Points to |
|-----|-----------|
| `skip_companies` | Blocklist text file — one company slug per line (`applications/skip_companies.txt`) |
| `application_index` | Optional HTML table of companies you already applied to (auto-merged into skip set). See [installation.md](installation.md) and [application-index-company-extraction-contract.md](application-index-company-extraction-contract.md) |
| `results_dir` | Where scrape CSVs land (`jobspy/results`) |
| `ops_rollup_dir` | Morning rollup exports for ops review |

**When:** Defaults work at onboarding; set `application_index` when you maintain an applied-companies HTML export.

---

### `tracks.enable`

**What it is:** Which scrape **channels** run in `jobspy/run_search_locally.py`.

| Track | Description |
|-------|-------------|
| **A** | General QA/SDET Indeed + LinkedIn style queries |
| **B** | Automation-focused query set |
| **C** | Contract / staff-aug patterns |
| **G** | Google Jobs |
| **R** | Remotive board |
| **GH** | Greenhouse company list (`config/ats_companies_gh.example.txt`) |
| **L** | Lever company list (`config/ats_companies_lever.example.txt`) |
| **AS** | Ashby company list (`config/ats_companies_ashby.example.txt`) |

**Example:** `enable: [A]` for a minimal first run; add boards once A looks healthy.

**When:** Onboarding — start small; expand later.

---

### `verified_remote_employers`

**What it is:** Employer name substrings you have **confirmed** are truly remote for you, even when LinkedIn JD copy is vague. Bypasses the arrangement post-gate in triage.

**What to put there:** Lowercase company fragments you trust.

**Example:** `verified_remote_employers: [example-corp, acme-remote-inc]`

**When:** Optional — usually **after** you verify one good posting from that employer, not day one.

---

### `review_companies`

**What it is:** Employers that **pass** scrape gates but should get `triage_verdict=review` instead of `apply` — extra manual tier/comp check before you spend time.

**What to put there:** Company substrings you want to treat cautiously.

**Example:** `review_companies: [crowdstrike, ifit solutions]`

**When:** Optional — add **after** you have run a few triage passes and know which employers need a second look.

---

### `ils` — Interview Likelihood Score (optional)

**ILS** is **Interview Likelihood Score**: a conservative 0–100-style **heuristic** from the JD (and optional per-company overrides), used only when triage runs **with** post-gates. It is **not** a hire score and **not** the same as `prescreen.priority`. Manual employer research lives outside this bundle.

| Key | Effect |
|-----|--------|
| `matrix_file` | D1–D5 formula YAML (`config/ils_matrix.yaml`) |
| `company_overrides_file` | Researched per-employer scores (optional JSON) |
| `cold_floor` | Your cold-tier baseline (default 45); pass the same value as `--ils-floor` when triaging |
| `referral_warm_delta` / `referral_strong_delta` | Lower the skip floor for companies listed as warm/strong in `referrals.status_file` |

ILS post-gating is **optional** after onboarding. Pipeline-only triage: `--no-post-gates`. Full rubric, travel penalty, and tier math: [ils-matrix.md](ils-matrix.md).

**When:** Skip at onboarding; tune `cold_floor` / matrix after a few triage runs if too many rows skip on `ils_below_*`.

---

## Related docs

- [Installation](installation.md) — manual setup and application index
- [ILS matrix](ils-matrix.md) — D1–D5 formula tuning
- [README](../README.md) — quick start and troubleshooting
