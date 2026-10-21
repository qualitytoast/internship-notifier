# Jane Street (`jane-street`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (00:15–00:35 UTC)

| | |
|---|---|
| Official careers URL | https://www.janestreet.com/join-jane-street/open-roles/. This is a chooser with two views: `?type=experienced-candidates` and `?type=students-and-new-grads`. Each view auto-adds a geo default (`&location=new-york` from the US), so pick **All Locations** to see everything (`&location=all-locations`). |
| Hiring system | Greenhouse. The site's own JSON `/jobs/main.json` is a copy of the Greenhouse board `janestreet`: same 221 ids, same titles. Greenhouse `absolute_url`s point back to the site (`/join-jane-street/apply/<id>?gh_jid=<id>`). |
| Recommended adapter | shared `greenhouse`, `{board: janestreet}`. Internships are recognised **only** through the `Employment Type` metadata, which the adapter already reads. |

## Which source is official/complete?
| Source | Jobs | What it is |
|---|---|---|
| `GET https://boards-api.greenhouse.io/v1/boards/janestreet/jobs` | **221** (`meta.total` 221) | system of record |
| `GET https://www.janestreet.com/jobs/main.json` | **221** | what the Open Roles page renders. Same id set as Greenhouse, and 0 title differences. Fields: `id, position, category, availability, city, overview, team, duration, min_salary, max_salary` |
| `GET https://www.janestreet.com/jobs/internships.json` | 49 rows, **no ids** | internship-programme directory (`position, location, department, team, duration, type, status`). All 49 have `status: "closed"`. 34 match an open posting in main.json, and 15 do not (HKG Dec–Feb winter programmes, NYC Co-Ops Jan–Apr and Sep–Dec, Mechanical Engineer NYC, Network Engineer NYC, Procurement HKG/LDN, …). |
| `/static/position-directories.json` | | **robots-disallowed** (`Disallow: /static/`), not needed |
| Ashby `jane` (23 jobs, from probe) | | **another company**: Jane App, clinic-management software in Canada. Ignore. |

Greenhouse and main.json are interchangeable. Use Greenhouse, because the shared adapter already exists and its metadata carries the same availability values.

## Recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/janestreet/jobs` (370 KB; add `?content=true` only if descriptions are needed).
- **Pagination:** none.
- **Job URL for emails:** the human page is `https://www.janestreet.com/join-jane-street/position/<id>/` (that is what the list links to). `absolute_url` is the apply page. Both are allowed by robots, except one specific id (`7304961002`, not currently listed).

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | e.g. 8599644002 |
| title | `jobs[].title` | Internship titles are plain role names: "Software Engineer", "Quantitative Trader", … They **never** contain "intern". |
| location(s) | `jobs[].location.name` | "New York, New York, United States" (89), "Hong Kong, Hong Kong" (58), "London, England, United Kingdom" (57), "Singapore" (15), "Austin, Texas, United States" (1), "Chicago" (1) |
| url | `jobs[].absolute_url`, or template `https://www.janestreet.com/join-jane-street/position/{id}/` | |
| posted date | `jobs[].first_published` | `updated_at` also present |
| employment type | `jobs[].metadata[name="Employment Type"].value` | `Full-Time: Experienced` (155), **`Summer Internship` (42)**, `Full-Time: New Grad` (24). The adapter's `_employment_type()` reads this, and filters.yaml `employment_types: [internship, …]` matches "Summer Internship". |
| other metadata | `Duration` | `Permanent` / `May-August` / `June-September` / `Flexible` |
| | `Workday Job Profile` | e.g. "Technology Intern", "Researcher" |
| | `Min salary` / `Max salary` | |
| | `Event *` | empty |
| department / team | none in the list response (main.json has `category`/`team`) | `?content=true` adds `departments[]` |

## Totals (observed 2026-10-20)
- **Feed, no filters:** **221** (Greenhouse `meta.total` = 221, and main.json = 221).
- **Live careers page, no filters:** **221 open postings**, observed with Playwright renders of both views after selecting "All Locations" in the page's own location dropdown:
  - Experienced Candidates: "**155 jobs** in all locations, all departments", with 155 unique `/position/<id>/` links.
  - Students and New Grads: "**81 jobs** in all types, all locations, all departments". Only **66** of them link to a posting (42 Summer Internship + 24 New Grad). The other **15** are the closed programme rows from `internships.json` that have no posting. They are not jobs.
  - So: 155 + 66 = 221 = feed. The geo default shows only New York (64 experienced, 30 students & new grads).
- **Intern/student:** **42**, all with Employment Type "Summer Internship" (31 May–Aug, 12 Jun–Sep, 2 "Flexible" Tools & Compilers R&D; 17 in NYC, the rest LDN/HKG/SGP). No co-ops are open.
  - The title regex alone finds only 1, and that one is a false positive: "Dean of Students, Academy of Math and Programming (AMP)", a staff job. So a title-only filter would miss every Jane Street internship.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/janestreet/jobs | ALLOW | no matching rule |
| https://www.janestreet.com/jobs/main.json | ALLOW | no matching rule |
| https://www.janestreet.com/jobs/internships.json | ALLOW | no matching rule |
| https://www.janestreet.com/static/position-directories.json | **BLOCK** | `Disallow: /static/` |
| https://www.janestreet.com/join-jane-street/open-roles/ | ALLOW | no matching rule |

## Anti-bot / quirks
- No bot protection seen (nginx, `cache-control: max-age=300`).
- **Homoglyph title:** job 8596771002 is titled `ꓟachine ꓡearning ꓣesearcher`, using Lisu letters U+A4DF, U+A4E1 and U+A4E3 in place of M, L and R (HKG Summer Internship). It is identical in Greenhouse and main.json, maybe a scraper canary. Keyword matching on "machine learning" fails for it. NFKC does not fold Lisu, so a small confusables map is needed if this should be classified. The employment type still marks it as an internship. 1 more title has an en dash.
- Do not treat `internships.json` "closed" rows as jobs. Do not treat `status: closed` as meaning the postings are closed: the 34 matching postings are open in Greenhouse.

## Recommended checker
```yaml
- key: jane-street
  name: Jane Street
  adapter: greenhouse
  settings:
    board: janestreet
    job_url: https://www.janestreet.com/join-jane-street/position/{id}/   # optional; absolute_url (apply page) also works
  careers_url: https://www.janestreet.com/join-jane-street/open-roles/
  # internships are flagged only by metadata "Employment Type" = "Summer Internship" (no "intern" in titles)
```

## Evidence
- Sample: `discovery/samples/jane-street.json` (trimmed). It has 10 raw Greenhouse jobs with metadata, 5 main.json items, and the whole internships.json.
- Playwright renders: open-roles chooser, both views with the geo default, and both views with All Locations (6 page loads). Also direct GETs of main.json, internships.json and the Greenhouse board.
