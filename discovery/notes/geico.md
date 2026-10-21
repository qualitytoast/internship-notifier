# GEICO (`geico`)

**Status:** verified-feed (one site watched; two other sites skipped)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.geico.com/ (www.geico.com/careers redirects there). It is a React single-page app behind Incapsula. Every "See Open Jobs" and location link goes to `https://geico.wd1.myworkdayjobs.com/External`. |
| Hiring system | Workday (tenant `geico`, wd1). robots.txt lists 3 public sites: `External`, `GEAP`, `GEAS`. |
| Recommended adapter | shared `workday`, `site: External` |

## Sites
| Site | Feed `total` | Page (Playwright) | What it is | Interns |
|---|---|---|---|---|
| `External` | **294** | "294 JOBS FOUND" | GEICO corporate jobs. The bookmark is a job on this site. | **5**: "Analyst Internship- Actuarial (CFO Org)", "Analyst Internship- Controllers (CFO Org)", "Analyst Internship Program - Finance & Operations Track (CFO Org)", "Human Resources Intern", "Marketing Intern". `jobFamilyGroup` "Internship" (id `da128ce5a1dc103e7c099155ab532262`) also gives 5. |
| `GEAS` (not watched) | 282 (281 at 03:19Z) | "282 JOBS FOUND" | Staff jobs at GEICO local agent offices ("Licensed Insurance Agent", "Entry Level Office Assistant"). Locations look like `GEA - TX Mesquite`. Not linked from careers.geico.com. No requisition is shared with `External`. | 0 |
| `GEAP` (not watched) | 0 | – | empty | – |

**GEAS has a malformed posting.** One `jobPostings[]` element is just `{"bulletFields": ["R0056265"]}`, with no `title` and no `externalPath`. The shared workday adapter's `need(p.get("externalPath") and "title" in p, …)` would raise a ShapeError on every run. If GEAS is ever added, the adapter must skip such rows and count them toward the total. A real browser renders the site's "282 JOBS FOUND" without complaint.

## Recommended feed
- `POST https://geico.wd1.myworkdayjobs.com/wday/cxs/geico/External/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. 20 per page, `total` on the first page only. Full run: 15 requests.
- Field map: the standard Workday one (`bulletFields[0]` = requisition, e.g. `R0066296`). The path suffix `-1` marks a reposting.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://geico.wd1.myworkdayjobs.com/wday/cxs/geico/External/jobs` | ALLOW | no matching rule. The file has `Allow: /External/`, `/GEAP/`, `/GEAS/` and `Disallow: /refreshFacet/`. |
| `https://careers.geico.com/` | ALLOW | no robots.txt |

## Recommended checker
```yaml
- key: geico
  name: GEICO
  careers_url: https://careers.geico.com/
  checker: workday
  settings: {host: geico.wd1.myworkdayjobs.com, tenant: geico, site: External}
  # GEAS = local-agency staff jobs (malformed row R0056265 breaks the adapter); GEAP is empty
```

## Evidence
- Sample: `discovery/samples/geico.json` holds the External first-page excerpt with facets, plus the malformed GEAS row.
- Requests: about 38 to geico.wd1 (External and GEAS enumerations, the intern-facet query, 2 renders, the recheck), plus 4 to careers.geico.com.
