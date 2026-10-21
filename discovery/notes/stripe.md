# Stripe (`stripe`)

**Status:** verified-feed (site lists 50 fewer; feed is the superset)   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://stripe.com/careers/search. The bookmark added `?locations=North+America&employment_types=Intern`, client-side filters. |
| Hiring system | **Greenhouse** board `stripe` behind a Next.js page. The page makes no Greenhouse XHR: the whole index is server-rendered into `__NEXT_DATA__` → `props.pageProps.jobIndexData` = `{filters: {teams, locations, tags, employmentTypes}, listings: [...]}`. Each listing has `greenhouseId`, `title`, `slug`, `locationIndices`, `teamIndices`, `tagIndices` and `employmentType`. Job pages are `https://stripe.com/careers/listing/<slug>/<greenhouseId>`. |
| Recommended adapter | shared `greenhouse` adapter, `board: stripe` |

## Recommended feed
- `GET https://boards-api.greenhouse.io/v1/boards/stripe/jobs` returns 726 jobs (`meta.total` 726). It is about 450 KB and has no pagination.
- `absolute_url` = `https://stripe.com/jobs/search?gh_jid=<id>`. It 307-redirects twice: to `/careers/listing/<slug>/<id>` for a listed job, or back to `/careers/search?gh_jid=<id>` for an unlisted one.
- `metadata` is empty and there is no employment-type field. Interns are recognisable by title. The site's own `employmentType` ("Intern") is only in `__NEXT_DATA__`.
- Every job has `company_name` "Stripe". Bridge and Privy roles appear only as site tags.

## Why the site shows 676, not 726
- The search page lists **676** jobs. On screen that is 1,236 job × office rows, 20 per page, "1 of 62". All 676 `greenhouseId`s are in the feed. **50 feed jobs are not listed on stripe.com**, and their `absolute_url` lands on the generic search page (checked for 8138044 "Account Executive, AI Sales").
- I found no single rule for which jobs are hidden:
  - 22 of the 50 are in Greenhouse department "Global Operations", which has no listed jobs.
  - The other 28 are scattered across departments that do have listed jobs (e.g. 2 of 33 in "1185 Account Executives (EMEA)").
  - 7 share a title with a listed job, e.g. extra "Software Engineer | Seattle" postings.
  - Offices and metadata look the same as for listed jobs.
- None of the 50 is a student role.
- **Use the feed.** It is a superset. The cost is up to 50 extra full-time jobs, which our filters drop anyway.

## Totals (observed 2026-10-19)
- **Feed, no filters:** **726**.
- **Live careers page, no filters:** **676** jobs. A Playwright render of /careers/search ("0 filters selected") showed 20 rows on page 1 and "1 of 62". The `__NEXT_DATA__` listings count is 676 jobs, and their location rows sum to 1,236, which is 62 pages of 20.
- **Intern/student:** **15**. The site's `employmentType: "Intern"` also counts 15, the same set. They are:
  - Software Engineer, Intern (x4)
  - Software Engineer, Intern (Summer or Winter) (x3)
  - PhD Data Scientist, Intern (x2)
  - Data Analyst, Intern (x2)
  - Financial Data Analyst Intern, Technical Operations
  - Integration Reliability Engineer Intern, Technical Operations
  - High School Internship, Software Engineering (Summer 2027)
  - Operations Associate, Apprenticeship

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/stripe/jobs | ALLOW | no matching rule |
| https://stripe.com/careers/search | ALLOW | no matching rule |
| https://stripe.com/jobs/search?gh_jid=8138044 · /careers/listing/<slug>/<id> | ALLOW | no matching rule |

## Anti-bot / quirks
- No challenge on stripe.com/careers.
- Optional: to list only what stripe.com shows, a checker could intersect with the `__NEXT_DATA__` listing ids from `GET https://stripe.com/careers/search`, a 370 KB HTML page. This is not recommended. It adds a fragile HTML dependency for no student-role benefit.

## Recommended checker
```yaml
- key: stripe
  name: Stripe
  adapter: greenhouse
  settings:
    board: stripe
  careers_url: https://stripe.com/careers/search
```

## Evidence
- Sample: `discovery/samples/stripe.json` is the `jobIndexData` object extracted from the `__NEXT_DATA__` of https://stripe.com/careers/search (676 listings with filters, 167 KB). The raw Greenhouse list is too big for a sample.
- I made a Playwright render of /careers/search and fetched the Greenhouse list, the departments list, 3 job details, and 2 `absolute_url` redirects (one listed, one unlisted).
