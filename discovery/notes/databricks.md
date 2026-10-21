# Databricks (`databricks`)

**Status:** verified-feed (page shows 6 fewer; explained)   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://www.databricks.com/company/careers/open-positions. The bookmark added `?department=University%20Recruiting&location=all`, a client-side filter that showed "19 results". The unfiltered page shows no count text. |
| Hiring system | **Greenhouse** board `databricks` behind a Gatsby site. The site does not call Greenhouse from the browser. It loads a build-time data file, `/careers-assets/page-data/company/careers/open-positions/page-data.json` (8.4 MB), whose `result.pageContext.data.allGreenhouseJob.nodes` holds every Greenhouse job, with `gh_Id`, `title`, `departments` and `metadata`. |
| Recommended adapter | shared `greenhouse` adapter, `board: databricks` |

There is no hosted board: `https://job-boards.greenhouse.io/databricks` 302-redirects to the careers page. `absolute_url` = `https://databricks.com/company/careers/open-positions/job?gh_jid=<id>`. The site's own links are `/company/careers/<category-slug>/<title-slug>-<id>`.

## Recommended feed
- `GET https://boards-api.greenhouse.io/v1/boards/databricks/jobs` returns 899 jobs, `meta.total` 899, no pagination, about 770 KB without `content`.
- Standard Greenhouse fields (see notes/walleye.md). The metadata has `Company Assignment` (legal entity) and **`Career Page Posting Category`** (multi-select). There is no employment-type field, so interns are found by title only.

## Why the page shows 893, not 899
- The page-data file holds **all 899** jobs, and its id set is identical to the API's. The page groups jobs into sections by `Career Page Posting Category`.
- 892 jobs have a non-empty category.
- 1 job has `null` and is still rendered under its Greenhouse department: 8843892002 GTM Motions & Skills Enablement Lead.
- **6 jobs have an empty list `[]`, and the page renders them nowhere:**
  - 7726495002 Account Executive, Singapore
  - 8638732002 Evergreen - FDE Brazil
  - 8334738002 Principal Engineer, Compute Fleet Management
  - 8540267002 Senior Staff Applied AI Engineer - Context Retrieval
  - 8476582002 Staff Software Engineer - Partner Ecosystem
  - 8815165002 Strategic Account Executive
- These 6 are still live on Greenhouse. None is a student role.
- **The Greenhouse feed is the complete source.** Use it. A student role posted with an empty category would be missing from the website but still caught by the feed.

## Totals (observed 2026-10-19)
- **Feed, no filters:** **899** (`meta.total` 899).
- **Live careers page, no filters:** **893**. In a Playwright render of /company/careers/open-positions, 893 distinct job links carried a Greenhouse id, all in the feed. One title is Japanese (デリバリーソリューションアーキテクト), so its slug is empty: `/delivery-solutions-architects/-8805655002`. The 6 missing ids are the empty-category jobs above.
- **Intern/student:** **13**. They are PhD GenAI Research Scientist Intern; Product Design Intern (2027 Start); PM Intern (Summer 2027) plus Amsterdam/Belgrade/Berlin variants; SWE Intern (2027) plus 2027-Start variants for Aarhus/Amsterdam/Belgrade/Berlin/London/"Winter". The bookmark's "University Recruiting" category view showed 19. That category holds the 13 interns, 5 new-grad roles, and 1 misfiled "Director, International Communications". Every intern is in that category today, but the checker should not rely on it.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/databricks/jobs | ALLOW | no matching rule |
| https://www.databricks.com/company/careers/open-positions | ALLOW | `Allow: /` |
| https://www.databricks.com/careers-assets/page-data/company/careers/open-positions/page-data.json | ALLOW | `Allow: /` (not needed by the checker) |

## Anti-bot / quirks
- The site is behind Cloudflare (rum/trace calls) but rendered without challenge.
- The page-data file is regenerated on deploys (last-modified 2026-10-20 00:05 GMT when fetched). Even so it matched the live API exactly, so the gap is the category rule, not staleness.

## Recommended checker
```yaml
- key: databricks
  name: Databricks
  adapter: greenhouse
  settings:
    board: databricks
  careers_url: https://www.databricks.com/company/careers/open-positions
```

## Evidence
- Sample: `discovery/samples/databricks.json` is the raw Greenhouse detail for 7726495002, one of the 6 hidden jobs. It shows `"Career Page Posting Category": []`.
- Capture: `discovery/captures/databricks/` (filtered bookmark). I made a Playwright render of the unfiltered page and fetched the page-data file once, the board list, the departments list, and one job detail.
