# Point72 (`point72`)

**Status:** verified-feed (careers site is a Salesforce mirror of the Greenhouse board, with re-titled jobs)   ·   **Checked:** 2026-10-20 (00:20–00:35 UTC)

| | |
|---|---|
| Official careers URL | https://careers.point72.com/ ("Browse Open Roles", "**213 Open Roles**"). It is a Salesforce Experience/Sites portal (server `sfdcedge`, Visualforce pages `CSCareerSearch` / `CSJobDetail`). |
| Hiring system | Greenhouse board **`point72`** (215). Every role on the site is a Salesforce `Job__c` record (`Job_Code__c` like `CSS-0012597`, `IVS-…`, `PIT-…`, `LSI-…`, `CPA-…`) whose `Apply_Now_URL__c` is a Greenhouse short link (`https://grnh.se/<code>`). 10 cards link straight to `boards.greenhouse.io/point72/jobs/<id>`. |
| Recommended adapter | shared `greenhouse`, `{board: point72}` |

## How the site maps to Greenhouse
- 213 cards on the page: **10** link directly to Greenhouse ids, and **203** link to `/CSJobDetail?jobName=<slug>&jobCode=<code>&location=<city>&locale=English&retURL=/CSCareerSearch`.
- Proof of the mapping, one sample: `CSJobDetail?jobCode=CSS-0012597` ("Quantitative Portfolio Manager", New York) → `Apply_Now_URL__c` `https://grnh.se/0e6f1b6f2us` → **301** `https://boards.greenhouse.io/point72/jobs/7046005002?gh_jid=7046005002` (Greenhouse title "**Cubist** Portfolio Manager", New York).
- The site re-titles jobs. 45 of the 203 Salesforce titles differ from the Greenhouse titles. The pairs below are matched by location; only the first mapping above is proven through grnh.se:
  - "Cubist Quantitative Researcher" → "Entry-Level Quantitative Researcher"
  - "Cubist Senior Data Scientist" → "Senior Data Scientist"
  - "Summer 2027 Quantitative Research Internship" → "Summer 2027 Quantitative Researcher Internship"
  - "Central Funding Application Delivery Manager" → "Application Delivery Manager, Central Funding Technology"
  - …

  Emails will show Greenhouse titles. That is fine: the words that matter for filtering are the same.
- **215 vs 213:** the page has no "Talent Network" card, and Greenhouse has exactly 2 such evergreen postings: "Investment Services Emerging Talent Network" (6732930002, 2023-09) and "Market Intelligence Emerging Talent Network" (6656054002, 2023-03). Everything else is on the site.

## Recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/point72/jobs` (158 KB, no pagination, `meta.total` 215).
- **Field map:**
  - `id`, `title`.
  - `location.name`: free text, e.g. "New York, NY", "Stamford, CT or New York, NY", "Dubai, Paris, Hong Kong, London, Sydney".
  - `absolute_url`: `https://boards.greenhouse.io/point72/jobs/<id>?gh_jid=<id>`.
  - `first_published`, `requisition_id`.
  - There is no employment-type metadata; titles carry "Intern"/"Internship".
- Not needed, for reference only: the Salesforce detail page embeds the `Job__c` record, with `Experience__c` ("Experienced Professionals" / …), `Type__c` ("Full Time"), `Area__c`, `Team__c`, `Business__c` ("Cubist"), `Posted_Location__c`, `Job_Description_External__c`. The site sitemap is `https://careers.point72.com/CSSitemap`.

## Totals (observed 2026-10-20)
- **Feed, no filters:** **215**.
- **Live careers page, no filters:** **213**. A Playwright render of https://careers.point72.com/ showed "213 Open Roles", with 213 unique cards (10 Greenhouse ids + 203 job codes). The 2026-10-19 capture showed 213 too.
- **Intern/student:** **18** by title (14 in the US). The US ones:
  - 2027 Summer Internship – Fundamental Researcher (Canvas); Investment Services (NY/Stamford); MS/PhD Data Scientist; Sector Analyst; Software Engineer
  - 2028 Point72 Academy Investment Analyst Summer Internship Program – US
  - Machine Learning Researcher – Intern; Micro-Intern: Research Technology Developer (IAP); Quantitative Developer Intern; Quantitative Researcher Intern; Quantitative Research Intern (NY/Seattle); Quantitative Research Intern (NLP); Quantitative Software Developer Intern; Summer 2027 Quantitative Research Internship

  Several of these are evergreen Cubist intern postings first published in 2024.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/point72/jobs | ALLOW | no matching rule |
| https://careers.point72.com/ and `/CSJobDetail?...` | ALLOW | `User-agent: *` / `Disallow:` (empty) |
| https://grnh.se/0e6f1b6f2us | ALLOW | no matching rule (one request, to prove the mapping) |

## Recommended checker
```yaml
- key: point72
  name: Point72
  adapter: greenhouse
  settings: {board: point72}
  careers_url: https://careers.point72.com/
```

## Evidence
- Sample: `discovery/samples/point72.json`. It has the raw Greenhouse list, an excerpt of the Salesforce `Job__c` record for CSS-0012597, and the grnh.se redirect.
- Capture: `discovery/captures/point72/page_0.html` (213 cards).
