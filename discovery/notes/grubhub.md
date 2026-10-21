# Grubhub (Wonder) (`grubhub`)

**Status:** verified-feed (2 Workday career sites of the parent company)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.grubhub.com/ ("View openings" goes to `https://wonder.wd1.myworkdayjobs.com/en-US/Grubhub_Careers`). Grubhub is part of Wonder. https://www.wonder.com/careers links `https://wonder.wd1.myworkdayjobs.com/WG`. |
| Hiring system | Workday (tenant **`wonder`**, wd1). robots.txt lists 2 public sites: `Grubhub_Careers` and `WG` (Wonder Group). |
| Recommended adapter | shared `workday`, `sites: [Grubhub_Careers, WG]` |

## Totals (observed 2026-10-20 UTC)
| Site | Feed `total` | Page (Playwright) | Requisitions only here | Interns |
|---|---|---|---|---|
| `Grubhub_Careers` | 36 | "36 JOBS FOUND" | 3 | 0 |
| `WG` | 78 | "78 JOBS FOUND" | 45 | 6 |
| **Deduped** | **81 requisitions** (114 postings; 33 are on both sites) | 114 | | **6** |

- `WG` carries 33 of Grubhub's 36 requisitions, plus Wonder's own jobs (food production, finance, logistics, HQ in NYC and Parsippany).
- All 6 internships are Wonder roles on `WG` only:
  - "Procurement Intern"
  - "Supply Chain Analytics Intern"
  - "Sourcing Associate Intern"
  - "Supply Chain Operations Intern"
  - "Process and Data Analysis Engineer Intern"
  - "Robotics Systems Engineer Intern"

  The `workerSubType` facet "Intern (Fixed Term)" (id `e09e1f6daade1000d4e775a112090000`) also gives 6. `Grubhub_Careers` has none today.
- The bookmark (`Grubhub_Careers?q=intern`, 15 hits) was keyword noise: no Grubhub posting is an internship.

## Recommended feed
- `POST https://wonder.wd1.myworkdayjobs.com/wday/cxs/wonder/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. Full run: 2 + 4 = 6 requests.
- Field map: the standard Workday one. The requisition is `bulletFields[0]` (`JR101424`). The same requisition is `…_JR101424` on `Grubhub_Careers` and `…_JR101424-1` on `WG`, so dedupe by req id.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://wonder.wd1.myworkdayjobs.com/wday/cxs/wonder/Grubhub_Careers/jobs` | ALLOW | no matching rule (`Allow: /WG/`, `Allow: /Grubhub_Careers/`) |
| `https://wonder.wd1.myworkdayjobs.com/wday/cxs/wonder/WG/jobs` | ALLOW | no matching rule |

## Recommended checker
```yaml
- key: grubhub
  name: Grubhub (Wonder)
  aliases: [Wonder]
  careers_url: https://careers.grubhub.com/
  checker: workday
  settings: {host: wonder.wd1.myworkdayjobs.com, tenant: wonder, sites: [Grubhub_Careers, WG]}
```

## Evidence
- Sample: `discovery/samples/grubhub.json` holds first-page excerpts of both sites with facets, including the WG interns.
- Requests: 10 to wonder.wd1 (enumerations, the intern-facet query, 2 renders), plus 1 each to careers.grubhub.com and www.wonder.com.
