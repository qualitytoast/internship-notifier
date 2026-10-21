# Walleye Capital (`walleye`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://www.walleyecapital.com/careers. Use no trailing slash: the bookmark `/careers/` returns 404, and the homepage nav links to `/careers`. |
| Hiring system | Greenhouse, **two boards**, both linked from the careers page. **Students → "apply now"** goes to `https://boards.greenhouse.io/walleyecapital-external-students`. **Experienced Candidates → "apply now"** goes to `http://boards.greenhouse.io/walleyecapital-external-fulltime`. |
| Recommended adapter | shared `greenhouse` adapter, run once per board token (or one company entry with a list of tokens) |

Search engines still show an older board, `walleyecapital-external-internships` (2025 postings). Its API now returns **404** because the board is retired, so do not use it. The obvious tokens `walleyecapital`, `walleye` and `walleye-capital` return 0 (discovery/probe_results.json).

## Recommended feed
- **Request 1 (students):** `GET https://boards-api.greenhouse.io/v1/boards/walleyecapital-external-students/jobs?content=true`
- **Request 2 (experienced):** `GET https://boards-api.greenhouse.io/v1/boards/walleyecapital-external-fulltime/jobs?content=true`
- **Headers:** a normal browser UA. No auth needed.
- **Pagination:** none. Each response holds every job on the board, and `meta.total` gives the count. `content=true` adds the description, departments and offices. Without it the response is smaller and still has title, location, absolute_url, updated_at and first_published.
- **Detail endpoint (optional):** `GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs/<id>`. Not needed when `content=true`.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | e.g. 4676334006. Use board+id or just id; ids are unique across Greenhouse. |
| title | `jobs[].title` | has trailing spaces on several full-time titles, so trim |
| location(s) | `jobs[].location.name` | free text, e.g. "Miami, FL", "New York, Chicago, or Miami". Structured: `jobs[].offices[].location` ("Miami, Florida, United States"). |
| url (detail/apply) | `jobs[].absolute_url` | `https://job-boards.greenhouse.io/<token>/jobs/<id>` |
| posted date | `jobs[].first_published` (ISO, with tz) | `updated_at` also present |
| description / snippet | `jobs[].content` | HTML-escaped HTML, so unescape then strip tags |
| employment type | none | use the title, e.g. "Intern (Summer 2027)", "(Full Time)" |
| department / team | `jobs[].departments[].name` | e.g. "Single Stock - Volatility" |
| other | `jobs[].requisition_id`, `jobs[].company_name` ("Walleye Capital Internships" / "Walleye Capital Full Time"), `jobs[].metadata` | |

## Totals (observed 2026-10-19)
- **Feed, no filters:** students **5** + full-time **12** = **17** (`meta.total` = 5 and 12).
- **Live careers pages, no filters:** job-boards.greenhouse.io/walleyecapital-external-students shows "**5 jobs**". job-boards.greenhouse.io/walleyecapital-external-fulltime shows "**12 jobs**". Both seen as text in a Playwright render. The walleyecapital.com/careers page itself lists no jobs; it only has the two buttons.
- **Intern/student:** **4**, all on the students board:
  - 4676334006 Equity Volatility Quant Researcher Intern (Summer 2027), Miami, FL
  - 4679184006 Quantic - PhD Quantitative Researcher Intern (Summer 2027), Boston, MA
  - 4679168006 Quantic – Quantitative Developer Intern (Summer 2027), Boston, MA
  - 4716166006 Special Projects Developer Intern (Summer 2027), New York, NY (first published 2026-10-01)
  
  The students board also has 1 campus full-time role (Fundamental Analyst - Volatility (Full Time)). Most full-time board postings are evergreen "submit your resume to a department" listings, first published 2025-06.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/walleyecapital-external-students/jobs?content=true | ALLOW | no matching rule |
| https://boards-api.greenhouse.io/v1/boards/walleyecapital-external-fulltime/jobs?content=true | ALLOW | no matching rule |
| https://job-boards.greenhouse.io/walleyecapital-external-students | ALLOW | no matching rule |
| https://boards.greenhouse.io/walleyecapital-external-students | ALLOW | no matching rule |
| https://www.walleyecapital.com/careers | ALLOW | robots.txt is 404, so allowed |

## Anti-bot / quirks
- No anti-bot measures on Greenhouse or walleyecapital.com (Apache).
- Walleye splits its jobs across two boards. Watching only one board misses jobs, so the checker must fetch both. The students board can include campus full-time roles.
- The board token has changed before (`…-external-internships` was retired). The 404-on-board and zero-after-nonzero health checks should flag the next rename. The careers page buttons are the source of truth for the token names.

## Recommended checker
```yaml
- key: walleye
  name: Walleye Capital
  adapter: greenhouse
  settings:
    boards: [walleyecapital-external-students, walleyecapital-external-fulltime]
    content: true
  careers_url: https://www.walleyecapital.com/careers
```

## Evidence
- Sample: `discovery/samples/walleye.json` (raw students board response, `?content=true`, 42 KB)
- Old capture: discovery/captures/walleye (404 on /careers/)
