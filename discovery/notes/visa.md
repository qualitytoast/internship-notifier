# Visa (`visa`)

**Status:** verified-feed (2 Workday career sites)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://corporate.visa.com/en/jobs/ redirects to `https://visa.wd5.myworkdayjobs.com/Visa`. The old students page `corporate.visa.com/en/jobs/students-and-graduates.html` now redirects to the same main site. The early-careers site `https://visa.wd5.myworkdayjobs.com/Visa_Early_Careers` (the bookmark) is a public site listed in robots.txt. |
| Hiring system | Workday (tenant `visa`, wd5). Public sites: `Visa`, `Visa_Early_Careers`. `Visa_Talent_Portal` is disallowed and not used. |
| Recommended adapter | shared `workday`, `sites: [Visa, Visa_Early_Careers]` |

## Recommended feed
- `POST https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. Headers: JSON content type and accept.
- 20 per page, `total` on the first page only. Full run: 43 + 2 = 45 requests. 846 jobs is well under the 2000 cap.
- Detail: `GET /wday/cxs/visa/<site><externalPath>` returns `jobPostingInfo.jobDescription`, `jobReqId` (e.g. `REF086121W`), `location` and `country`.

## Field map
Same as every Workday site:
- id: `externalPath`
- requisition: `bulletFields[0]`, e.g. `REF089602W`
- title: `title`
- location: `locationsText`, e.g. "GB - London, United Kingdom"
- url: `https://visa.wd5.myworkdayjobs.com/en-US/<site><externalPath>`
- posted: `postedOn`, relative

Slugs can be stale: `VCA-Intern--IDS-_REF086121W` is titled "Data Science Intern".

## Totals (observed 2026-10-20 UTC)
| Site | Feed `total` | Page (Playwright) | Interns |
|---|---|---|---|
| `Visa` | 846 (847 at the 03:19Z recheck) | "846 JOBS FOUND" | 5, all also on Early Careers |
| `Visa_Early_Careers` | 31 | "31 JOBS FOUND" | 23 |
| **Deduped** | **867 requisitions** (877 postings; 10 requisitions are on both sites) | 877 | **23** |

- 18 of the 23 internships are only on `Visa_Early_Careers`. Examples:
  - all "… Intern - Students Graduating Summer 2028 or December 2027" roles
  - "Software Engineer Placement Year"
  - "COOP Trainee"
  - the two Morocco interns
- The main site's 5 interns are "Data Science Intern", "Marketing Intern" and three "Staff Research Scientist, Intern - PhD …" roles. All 5 are duplicates of early-careers postings.
- The early-careers site also has a few graduate and full-time roles ("Data Science Graduate", "Manager, Client Consulting").
- The `jobFamily` facet "Intern" agrees: 23 on Early Careers and 5 on Visa.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa/jobs` | ALLOW | no matching rule |
| `https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa_Early_Careers/jobs` | ALLOW | no matching rule |
| `https://visa.wd5.myworkdayjobs.com/Visa_Talent_Portal/…` | BLOCK | `Disallow: /Visa_Talent_Portal/`. Not used. |

## Quirks
- The same requisition has different paths on the two sites. Dedupe by `bulletFields[0]` to avoid two emails per internship.
- corporate.visa.com is an Angular app. Its students URL now triggers a `search.visa.com/CAREERS/careers/job?refNumber=…` 404 and then redirects to the Workday main site, so the corporate site no longer lists jobs itself.

## Recommended checker
```yaml
- key: visa
  name: Visa
  careers_url: https://corporate.visa.com/en/jobs/
  checker: workday
  settings: {host: visa.wd5.myworkdayjobs.com, tenant: visa, sites: [Visa, Visa_Early_Careers]}
```

## Evidence
- Sample: `discovery/samples/visa.json` holds first-page excerpts and facets for both sites.
- Requests: 49 to visa.wd5 (2 full enumerations, the intern-facet query and 2 renders), plus 5 to corporate.visa.com.
