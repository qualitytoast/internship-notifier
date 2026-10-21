# Nutanix (`nutanix`)

**Status:** verified-feed, needs a small Jobvite checker (`custom:jobvite`, worth making a shared `jobvite` adapter)   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careers.nutanix.com/en/jobs/ (bookmark: the same page with `type=Internship`; it currently shows "Sorry, there are no results"). It is an Umbraco "jobboard" marketing site. |
| Hiring system | **Jobvite**, company id `qKr9VfwZ`, careers slug `nutanix`. Every job page's "Apply Now" goes to `https://app.jobvite.com/CompanyJobs/Careers.aspx?k=Apply&j=<jobId>&c=qKr9VfwZ`. The marketing site's job ids are the Jobvite **requisition ids**: `/en/jobs/32891/systems-reliability-engineer/` is `<requisitionid>32891</requisitionid>`, Jobvite job `oIqXAfwp`. The talent community form is on Findem (`crm.findemtalent.com`) and is not a job source. |
| Recommended adapter | `custom:jobvite`, a single XML GET (spec below). It would also serve as a shared `jobvite` adapter for any other Jobvite company. |

## Recommended feed
- **Request:** `GET https://app.jobvite.com/CompanyJobs/Xml.aspx?c=qKr9VfwZ` returns `text/xml; charset=utf-8`, 6.8 MB.
- **Headers:** a browser UA. No auth or cookies needed. Plain httpx got 200.
- **Pagination:** none. One response holds every posting.
- **Structure:** `<result><job>…</job>…</result>`. Each `<job>` has `id`, `externalJobPostingId`, `title`, `requisitionid`, `category`, `jobtype`, `region`, `location`, `date` (M/D/YYYY), `detail-url`, `apply-url`, `description` (HTML, entity-escaped), `briefdescription`, `business_x0020_unit`, `hiring_x0020_team`, `workflow`, `referral_x0020_bonus` and `agency_x0020_access`. Parse with `lxml` (`huge_tree=True`), because some descriptions are large.
- **One row per location:** a requisition posted in several cities produces several `<job>` rows. They share `requisitionid`, title and date. The primary row's `id` is `olyvAfwI`, and the location rows are `olyvAfwI-Cr5lVfww`, `olyvAfwI-CyWtVfwC`, … For example, "AI Portfolio Sales Specialist - Germany" has 13 rows. **Dedupe by `requisitionid`** (or by `id` before the first `-`) and join the locations. That gives the site's count.
- **Alternatives (not needed):** `https://jobs.jobvite.com/nutanix/jobs` is Jobvite's hosted HTML list. It shows only 125 links plus per-category "search?c=…&p=0" pagers, so it is more work and no more complete.

## Field map
| Job field | XML element | Notes |
|---|---|---|
| id | `requisitionid` (after dedupe) | e.g. 32891. Keep the Jobvite `id` of the primary row too. |
| title | `title` | |
| location(s) | `location` of every row with that requisition | "Sydney, Australia", "Mexico City, Mexico". `region` is AMER, EMEA, India or APAC. |
| url | `https://careers.nutanix.com/en/jobs/<requisitionid>/<slug>/` or `https://jobs.jobvite.com/nutanix/job/<id>` | The feed's `detail-url` is `http://app.jobvite.com/CompanyJobs/Job.aspx?c=qKr9VfwZ&j=<id>` (robots-allowed). Prefer https. |
| posted date | `date` | "10/19/2026" (US M/D/YYYY) |
| description | `description` | HTML. `briefdescription` is shorter. |
| employment type | `jobtype` | Full-Time 396, **Evergreen 24**, Fixed-term Contract 2, New Grad 1, Contractor 1, Part-Time 1 (rows) |
| department | `category` | Sales 238, Engineering 57, Product Support 37, … (rows) |

## Totals (observed 2026-10-19)
- **Feed, no filters:** **283** requisitions (425 `<job>` rows, 425 unique row ids). 55 requisitions have more than one row.
- **Live careers page, no filters:** **283**, "Displaying 1 to 20 of 283 matching jobs" in a Playwright render of `/en/jobs/`. Its first six cards (32906, 32902, 32892, 32891, 32888, 32887) are requisition ids from the feed.
- **Intern/student:** **2** by the title rule. Neither has jobtype "Internship". Both are "Evergreen", which is why the bookmark's `type=Internship` filter is empty:
  - Systems Reliability Engineer Intern (2027), Mexico City, Mexico
  - Technical Support Intern, Barcelona, Spain (Fall 2026)

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://app.jobvite.com/CompanyJobs/Xml.aspx?c=qKr9VfwZ | ALLOW | no matching rule. app.jobvite.com disallows `/API/`, `/Careers/`, `/Jobs/`, `/Company/`, … and, under `/CompanyJobs/`, only `PreviewApplication.aspx`. |
| https://app.jobvite.com/CompanyJobs/Job.aspx?c=qKr9VfwZ&j=oIqXAfwp | ALLOW | no matching rule |
| https://jobs.jobvite.com/nutanix/jobs | ALLOW | robots.txt is 404 |
| https://careers.nutanix.com/en/jobs/ | ALLOW | `Allow: /` |

## Anti-bot / quirks
- No challenge on app.jobvite.com. The careers.nutanix.com pages were only rendered in Playwright, and the checker does not need them.
- The feed is large (6.8 MB) because it includes full descriptions. Fetch it once per run.
- Jobvite location rows can be vague ("Germany", "France, France") next to city rows for the same requisition.

## Recommended checker
```yaml
- key: nutanix
  name: Nutanix
  adapter: jobvite            # new: GET https://app.jobvite.com/CompanyJobs/Xml.aspx?c=<company_id>
  settings:
    company_id: qKr9VfwZ
    slug: nutanix             # for https://jobs.jobvite.com/<slug>/job/<id> links
    dedupe_by: requisitionid  # one row per location in the feed
  careers_url: https://careers.nutanix.com/en/jobs/
```

## Evidence
- Sample: `discovery/samples/nutanix.xml` holds the first 8 `<job>` elements of the feed, cut at a `</job>` boundary and closed, so it is well-formed (100 KB of the 6.8 MB).
- Capture: `discovery/captures/nutanix/` (bookmark: Internship filter, no results).
- Requests: 1 XML feed, 1 jobs.jobvite.com list, and 2 Playwright renders (`/en/jobs/` and one job page).
