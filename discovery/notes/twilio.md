# Twilio (`twilio`)

**Status:** verified-feed (the Greenhouse API is the source of record; the Eightfold site mirrors it)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://www.twilio.com/en-us/company/jobs redirects to `https://jobs.twilio.com/careers`, an Eightfold PCSX site with domain `twilio.com`. That site is the bookmark. |
| Hiring system | **Greenhouse** board `twilio` (the ATS) with an **Eightfold** career site in front of it |
| Recommended adapter | shared `greenhouse`, `board: twilio` |

## Greenhouse and Eightfold are the same data
- `GET https://boards-api.greenhouse.io/v1/boards/twilio/jobs` returns `meta.total` **134** job posts, which are **133 distinct jobs**. One job is posted twice: internal_job_id `3478436`, requisition `50551`, "Security Engineer, Incident Response", once for "Remote - Ireland" (post 8023560) and once for "Remote - United Kingdom" (post 8055481).
- `GET https://jobs.twilio.com/api/pcsx/search?domain=twilio.com&query=&location=&start=N` returns `count` **133**. Every Eightfold position maps 1:1 to Greenhouse: `atsJobId` = GH `internal_job_id` and `displayJobId` = GH `requisition_id`, 133 of 133.
- Page: a Playwright render of https://jobs.twilio.com/careers showed "133 jobs", "Page 1 of 14".
- Interns: **0** on both today. The bookmark (`query=intern`) shows 4 fuzzy keyword hits, none of them internships.

Greenhouse is better: one request with no paging, `updated_at`/`first_published`, `content=true` for descriptions, and no Eightfold rate-limit or ordering problems.

## Recommended feed
- `GET https://boards-api.greenhouse.io/v1/boards/twilio/jobs`. Add `?content=true` for descriptions and departments.
- Job URL: `absolute_url`, which is `https://job-boards.greenhouse.io/twilio/jobs/<id>`. Checked: HTTP 200, "Job Application for … at Twilio". The Eightfold URL for the same job is `https://jobs.twilio.com/careers/job/<eightfold id>`, which cannot be built from Greenhouse data.
- Keep the two posts of job 3478436 as two jobs (one per location), or collapse them on `internal_job_id`.

## Eightfold facts (for reference)
- 10 per page. `page_size=20` returns 400, and v2 returns 403.
- **`postedTs` is 0 on all 133 positions**, so `sort_by=timestamp` sorts nothing. The order is roughly by Eightfold id, descending, with 10 inversions. A newest-first quick scan would not be safe here, which is another reason to use Greenhouse.
- No 429 in 24 requests. The filters offer only `skills` in the API, and the UI adds location, department and experience.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://boards-api.greenhouse.io/v1/boards/twilio/jobs` (and `?content=true`) | ALLOW | no matching rule |
| `https://job-boards.greenhouse.io/twilio/jobs/8177722` | ALLOW | no matching rule |
| `https://jobs.twilio.com/api/pcsx/search?domain=twilio.com&…` | ALLOW | `Allow: /api/pcsx` |

## Recommended checker
```yaml
- key: twilio
  name: Twilio
  careers_url: https://www.twilio.com/en-us/company/jobs
  checker: greenhouse
  settings: {board: twilio}
```

## Evidence
- Sample: `discovery/samples/twilio.json` holds the two Greenhouse posts of job 3478436 plus 3 more, and Eightfold search page 1.
- Requests: 3 to boards-api.greenhouse.io and 1 to job-boards.greenhouse.io; 24 to jobs.twilio.com (enumeration, experiments, 2 renders).
