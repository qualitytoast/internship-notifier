# Hudson River Trading (`hudson-river-trading`)

**Status:** verified-feed (main board + small evergreen talent-community board)   ·   **Checked:** 2026-10-20 (00:25–00:35 UTC)

| | |
|---|---|
| Official careers URL | https://www.hudsonrivertrading.com/careers/ (WordPress). The job list is loaded with `POST /wp-admin/admin-ajax.php` and links to `/hrt-job/<slug>/` pages. Students: https://www.hudsonrivertrading.com/student-opportunities/ |
| Hiring system | Greenhouse. **`wehrtyou`** holds every listed job: its `absolute_url`s are `https://www.hudsonrivertrading.com/careers/job/?gh_jid=<id>`. **`hrttalentcommunity`** holds 3 evergreen talent-pool postings; two of them are the "Campus Talent Community" / "Experienced Talent Community" "↳ Join Today" cards at `/careers/#talentcommunity`. Ashby `hrt` = 0; Greenhouse `hudsonrivertrading`, `hrt` = 0. |
| Recommended adapter | shared `greenhouse`, `{boards: [wehrtyou, hrttalentcommunity]}`. The second board is optional: 3 evergreen postings, one of which mentions internships. |

## Recommended feed
- `GET https://boards-api.greenhouse.io/v1/boards/wehrtyou/jobs` → 86 (101 KB)
- `GET https://boards-api.greenhouse.io/v1/boards/hrttalentcommunity/jobs` → 3
- **wehrtyou metadata:**
  - `Employment Type`: "Full-Time" 80 / "Intern" 6. The shared adapter reads this field.
  - `Job Type`: ["Full-Time: Experienced"] 74 / ["Full-Time: New Grad"] 6 / ["Internship"] 6.
  - Also `Job Category`, `Role Priority`, `Career Site Metadata`, `Career Site Ranking`.
- **hrttalentcommunity:**
  - 3432773 "Campus Talent Community" (All Offices, first published 2021-08)
  - 3530960 "HRT Talent Community" (All Offices, 2021-09)
  - 4576493 "FPGA Verification and Developer (Internships and Campus Full-time)" (New York, 2022-09)

## Totals (observed 2026-10-20)
- **Feed, no filters:** 86 + 3 = **89**.
- **Live careers page, no filters:** **86 job cards + 2 talent-community cards**. A Playwright render of /careers/ (scrolled) gave 86 unique `/hrt-job/<slug>/` links. Their titles are exactly the 78 distinct titles on wehrtyou; some titles repeat across locations. The FPGA talent posting is not linked from /careers/.
- **Intern/student:** **7**. 6 on wehrtyou (Employment Type Intern), all with a US office:
  - Algorithm Development (Quant Research & Trading) Internship – Summer 2027, and the PhD Internship – Summer 2027 (London/NY/Singapore)
  - Data Scientist Intern – 2027 (London/NY)
  - Hardware Engineer Internship – Summer 2027 (NY)
  - PhD Winter Internship – 2027 (NY)
  - Software Engineering Internship (C++ or Python) – Summer 2027 (Austin/Chicago/London/NY/Singapore)

  The 7th is the evergreen FPGA talent posting.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/wehrtyou/jobs | ALLOW | no matching rule |
| https://boards-api.greenhouse.io/v1/boards/hrttalentcommunity/jobs | ALLOW | no matching rule |
| https://www.hudsonrivertrading.com/careers/ | ALLOW | no matching rule |

## Anti-bot / quirks
- Plain HTTP `GET /student-opportunities/` returned **403 Forbidden** (a 103-byte nginx-style page). The careers page renders normally in a browser. The checker only needs the Greenhouse API.

## Recommended checker
```yaml
- key: hudson-river-trading
  name: Hudson River Trading
  adapter: greenhouse
  settings: {boards: [wehrtyou, hrttalentcommunity]}   # hrttalentcommunity optional (3 evergreen talent pools)
  careers_url: https://www.hudsonrivertrading.com/careers/
```

## Evidence
- Sample: `discovery/samples/hudson-river-trading.json` (both raw board responses).
- Capture: `discovery/captures/hudson-river-trading/`. Playwright render of /careers/ on 2026-10-20 (86 job links).
