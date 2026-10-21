# C3 AI (`c3-ai`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://c3.ai/careers. It is a Next.js/Payload site on Vercel. The "Current Openings" list shows 3 cards plus a **View all** button. Job links are `https://c3.ai/job-description/<gh id>?gh_jid=<id>`. |
| Hiring system | Greenhouse, **two boards**. **`c3iot`** is the main board: every card on c3.ai is a c3iot job (`company_name` "C3 AI"). **`c3ascend`** is "C3 AI Ascend Internship Program: Summer 2027". The page's "Interns and Early Professionals → Explore our open roles now" button links to `https://boards.greenhouse.io/c3ascend`. |
| Recommended adapter | shared `greenhouse` adapter with `boards: [c3iot, c3ascend]`, deduped by `requisition_id` (see below) |

## Recommended feed
- **Requests:** `GET https://boards-api.greenhouse.io/v1/boards/c3iot/jobs` and `GET https://boards-api.greenhouse.io/v1/boards/c3ascend/jobs`
- **Pagination:** none. `meta.total` is 94 and 3.
- **Fields:** standard Greenhouse list (see notes/walleye.md), plus metadata `Employment Type` (`Full-Time` / `Regular` / `Intern`). The adapter maps this to employment_type.
- **URLs:** c3iot `absolute_url` is `https://c3.ai/job-description/<id>?gh_jid=<id>`. c3ascend's is `https://job-boards.greenhouse.io/c3ascend/jobs/<id>`.

## Duplicates
c3ascend's 3 postings are **copies of c3iot postings**. They have different job ids and the same `requisition_id`:

| req | c3iot id | c3ascend id | title |
|---|---|---|---|
| 1448 | 8860563002 | 8860562002 | AI Product Manager - MBA Intern (Summer 2027) |
| 1399 | 8738918002 | 8738917002 | Data Science - Intern (Summer 2027) |
| 1400 | 8739037002 | 8739036002 | Software Engineer - Intern (Summer 2027) |

Fetching both boards without a dedupe step gives two alerts per Ascend intern role. Dedupe on `requisition_id`, or on title plus city: c3iot writes "Redwood City, California, United States" and c3ascend writes "Redwood City, CA". Keep c3ascend anyway, in case Ascend posts something that is not on c3iot.

## Totals (observed 2026-10-19)
- **Feed, no filters:** c3iot **94** + c3ascend 3 = 97 postings. Deduped by requisition that is **94**.
- **Live careers page, no filters:** **94**. A Playwright render of c3.ai/careers, after clicking "View all", showed 94 `/job-description/<id>` cards. Their ids are exactly the c3iot feed. The server HTML (Vercel cache HIT) also embeds all 94 ids. The hosted job-boards.greenhouse.io/c3ascend page shows "3 jobs".
- **Intern/student:** **5** unique, all Summer 2027:
  - AI Product Manager - MBA Intern (Redwood City)
  - Data Science - Intern (Redwood City)
  - Software Engineer - Intern (Redwood City)
  - Software Engineer - Intern (Guadalajara)
  - QA Engineer - Intern (Guadalajara)

  The 3 c3ascend copies are not counted again. c3iot has an "Internships" department with 5 jobs.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/c3iot/jobs · .../c3ascend/jobs | ALLOW | no matching rule |
| https://c3.ai/careers · https://c3.ai/job-description/8860563002 | ALLOW | `Allow: /` |
| https://job-boards.greenhouse.io/c3ascend | ALLOW | no matching rule |

## Anti-bot / quirks
- None. The capture's "of 10" / "of 4" count texts come from the parental-leave benefit text ("a total of 10 to 12 weeks", "a total of 4 weeks"), not job counts.
- The probe's `c3iot` token is not visible anywhere on c3.ai. It is confirmed only by the id match and by `absolute_url` pointing to c3.ai.

## Recommended checker
```yaml
- key: c3-ai
  name: C3 AI
  adapter: greenhouse
  settings:
    boards: [c3iot, c3ascend]
    dedupe_on: requisition_id      # c3ascend repeats c3iot intern requisitions
  careers_url: https://c3.ai/careers
```

## Evidence
- Sample: `discovery/samples/c3-ai.json` is the raw `c3ascend` board list (3 jobs).
- I made Playwright renders of c3.ai/careers before and after "View all" and of job-boards.greenhouse.io/c3ascend. I also fetched both board lists, the c3iot departments list, and one plain GET of c3.ai/careers.
