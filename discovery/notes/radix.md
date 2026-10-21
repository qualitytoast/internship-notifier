# Radix Trading (`radix`)

**Status:** verified-feed (two Greenhouse boards)   ·   **Checked:** 2026-10-20 (00:20–00:30 UTC)

| | |
|---|---|
| Official careers URL | https://www.radixtrading.com/#careers. The home page's careers section has two buttons: **Experienced** → `https://boards.greenhouse.io/radixexperienced` and **University** → `https://boards.greenhouse.io/radixuniversity`. The bookmark was the university board only. `www.radix.trading` ("Radix • Where Smart Money Trades Crypto") is an unrelated crypto company. |
| Hiring system | Greenhouse, **two boards**: `radixexperienced` (company_name "Radix Trading Experienced Job Board") and `radixuniversity` ("Radix Trading University Job Board"). Probes `radix`, `radixtrading` and `radix-trading` return 404/0. |
| Recommended adapter | shared `greenhouse`, `{boards: [radixexperienced, radixuniversity]}` |

## Recommended feed
- `GET https://boards-api.greenhouse.io/v1/boards/radixexperienced/jobs` → 7
- `GET https://boards-api.greenhouse.io/v1/boards/radixuniversity/jobs` → 8
- No pagination. Standard Greenhouse field map:
  - `id`, `title` (trim the trailing spaces), `location.name`, `absolute_url` (`https://job-boards.greenhouse.io/<board>/jobs/<id>`), `first_published`.
  - `location.name` looks like "Chicago, Illinois, United States; New York, New York, United States; Radix Trading Amsterdam" on the experienced board and "Chicago, New York, Amsterdam" on the university board.
- The two boards carry similar titles but different posting ids. Example: "Quantitative Business Analyst" is 8468817002 (experienced) and 8080910002 (university). Keep both; ids are unique across Greenhouse.

## Totals (observed 2026-10-20)
- **Feed, no filters:** 7 + 8 = **15**.
- **Live pages, no filters:**
  - job-boards.greenhouse.io/radixexperienced: "**7 jobs**", 7 job links (Playwright, 2026-10-20).
  - job-boards.greenhouse.io/radixuniversity: "**8 jobs**" (Playwright capture, 2026-10-19). The 8 ids are equal to the API's.
- **Intern/student:** **1**, "Quantitative Technologist (C++ Intern)" (8500265002, Chicago).
  - The rest of the university board is campus full-time: Quantitative Researcher (Master's/Bachelor's; PhD+), Quantitative Technologist (C++ Developer; DevOps – Night Shift; DevOps & Systems Engineering; FPGA Engineer, PhD), Quantitative Business Analyst.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/radixexperienced/jobs | ALLOW | no matching rule |
| https://boards-api.greenhouse.io/v1/boards/radixuniversity/jobs | ALLOW | no matching rule |
| https://www.radixtrading.com/ | ALLOW | no matching rule |

## Recommended checker
```yaml
- key: radix
  name: Radix Trading
  adapter: greenhouse
  settings: {boards: [radixexperienced, radixuniversity]}
  careers_url: https://www.radixtrading.com/#careers
```

## Evidence
- Sample: `discovery/samples/radix.json` (both raw board responses).
- Capture: `discovery/captures/radix/` (university board page, "8 jobs").
