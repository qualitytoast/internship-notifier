# Robinhood (`robinhood`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careers.robinhood.com/ (an Instapage landing page that lists every job) |
| Hiring system | Greenhouse, **two boards loaded by the page in the browser**:<br>- `api.greenhouse.io/v1/boards/robinhood/jobs` (151 jobs)<br>- `api.greenhouse.io/v1/boards/sherwoodmedia/jobs` (**0 jobs today**)<br>It also loads both boards' `/offices`. |
| Recommended adapter | shared `greenhouse` adapter, `boards: [robinhood, sherwoodmedia]` |

`sherwoodmedia` is Sherwood Media (Sherwood News), Robinhood's news brand. The careers page merges it, so keep it: its postings will appear there when it has any. The board exists and returns `{"jobs":[],"meta":{"total":0}}` (HTTP 200), so the 404-on-board health check won't fire. Because it has always been 0, the zero-after-nonzero check won't fire either.

## Recommended feed
- **Request 1:** `GET https://boards-api.greenhouse.io/v1/boards/robinhood/jobs`
- **Request 2:** `GET https://boards-api.greenhouse.io/v1/boards/sherwoodmedia/jobs`
- **Headers and pagination:** a normal UA, no pagination, and `meta.total` equals the number of jobs.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | |
| title | `jobs[].title` | |
| location(s) | `jobs[].location.name` | e.g. "Denver, CO", "Menlo Park, CA" |
| url | `jobs[].absolute_url` | `https://boards.greenhouse.io/robinhood/jobs/<id>?t=gh_src=&gh_jid=<id>` has an odd query string. The page links `...?gh_src=NaN&gh_jid=<id>`. A clean form is `https://job-boards.greenhouse.io/robinhood/jobs/<id>`. |
| posted date | `jobs[].first_published` | |
| employment type | none in the list metadata | match on the title |
| department / team | `departments[]` in the detail call | |

## Totals (observed 2026-10-20)
- **Feed, no filters:** robinhood **151** + sherwoodmedia **0** = **151**.
- **Live careers page, no filters:** **151**. The page shows no count text. A Playwright render of https://careers.robinhood.com/ had 151 unique `boards.greenhouse.io/robinhood/jobs/<id>` links, the same as the feed.
- **Intern/student:** **2**:
  - 8198241 Fraud Operations Intern (Summer 2027), Denver, CO
  - 8198187 Investment Analyst MBA Intern, Robinhood Ventures (Summer 2027), Menlo Park, CA

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/robinhood/jobs | ALLOW | no matching rule |
| https://boards-api.greenhouse.io/v1/boards/sherwoodmedia/jobs | ALLOW | no matching rule |
| https://careers.robinhood.com/ | ALLOW | no robots.txt |

## Anti-bot / quirks
- None seen. The page uses the older `api.greenhouse.io/v1/boards/...` host. Use `boards-api.greenhouse.io`, which serves the same data.

## Recommended checker
```yaml
- key: robinhood
  name: Robinhood
  adapter: greenhouse
  settings:
    boards: [robinhood, sherwoodmedia]
  careers_url: https://careers.robinhood.com/
```

## Evidence
- Sample: `discovery/samples/robinhood.json` is the raw `robinhood` board response (151 jobs, 112 KB).
- Capture: `discovery/captures/robinhood/` (the same page; it shows both board fetches).
