# Kirin (`kirin`)

**Status:** verified-feed (the Ashby board is the right company, but it is a multi-brand group board)   ·   **Checked:** 2026-10-20 (00:10–00:25 UTC)

| | |
|---|---|
| Official careers URL | https://jobs.ashbyhq.com/kirin (Ashby-hosted page "Kirin Jobs", "Open Positions (27)"). https://kirin.com/ ("Kirin – A Trading Company") is a canvas/WebGL single-page app with no text, links or careers section. Its JS bundle contains no careers, jobs or ATS references. |
| Hiring system | Ashby, organisation **"Kirin"**, slug `kirin` / `Kirin`. |
| Recommended adapter | shared `ashby`, `{board: kirin}` |

## Is this the 2025 NYC prediction-markets trading firm?
Yes, the same organisation:
- The Ashby hosted page's app data says `organization.name = "Kirin"` and `publicWebsite = "https://kirin.com/"`. The page's logo also links to kirin.com, the "A Trading Company" site.
- Built In NYC's company profile "Kirin" (NYC, founded 2025, 26 employees, tagged Blockchain / Fintech / Crypto / Financial Services, website kirin.com) lists exactly postings that are on this Ashby board: "Personal Assistant - NYC", "CG Motion Designer – Consumer Hardware", "3D Product Visualization Artist", "Freelance CG Artist - Product Rendering & Video".
- The prediction-markets role was "Quantitative Research Intern – Prediction Markets" (Built In job 8073409, hybrid NYC; Simplify lists a Fall 2026 version posted 2026-07-21, SF + NY). **It has been removed.** Today the board has **no trading or prediction-markets postings.**

**Caveat:** this board hosts the whole Kirin group, not just the trading business. The departments are brands:

| Department | Postings |
|---|---|
| Italic (DTC goods, mostly Shenzhen) | 11 |
| Sudo (consumer hardware) | 7 |
| Family (NYC personal/property staff, Foshan furniture sourcing) | 5 |
| Courtly (online weddings) | 1 |
| Blemish | 1 |
| Kati | 1 |
| Kirin | 1 |

The filters (field + US location) will drop almost all of these. Keep the board, because new Kirin trading / quant-research internships would be posted here (department "Kirin").

## Recommended feed
- **Request:** `GET https://api.ashbyhq.com/posting-api/job-board/kirin?includeCompensation=false` (shared adapter). `jobs.ashbyhq.com/api/*` is robots-disallowed; the public posting API is the documented feed.
- **Field map:** the standard Ashby posting API.
  - `id` (uuid), `title` (often bilingual Chinese/English), `location` + `secondaryLocations[].location`, `jobUrl` (`https://jobs.ashbyhq.com/kirin/<uuid>`), `publishedAt`, `employmentType`.
  - `employmentType` values: FullTime 14, PartTime 8, Contract 4, Intern 1.
  - `department` / `team` hold the brand name. `descriptionPlain`.

## Totals (observed)
- **Feed, no filters:** **27** (2026-10-20). All `isListed` true.
- **Live careers page, no filters:** **27**. The 2026-10-19 Playwright capture of jobs.ashbyhq.com/kirin shows "Open Positions (27)", and the page's own GraphQL call returned 27 postings.
- **Intern/student:** **1**: "VC Intern 风险投资实习生" (department Kirin, Shenzhen, employmentType Intern, published 2025-12-27). There are no US internships.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://api.ashbyhq.com/posting-api/job-board/kirin?includeCompensation=false | ALLOW | no robots.txt (401) → allowed |
| https://jobs.ashbyhq.com/kirin | ALLOW | no matching rule |
| https://kirin.com/ | ALLOW | the file has only Cloudflare content-signal comments, no rules |

## Other tokens tried (all 404)
- Ashby: `kirintrading`, `kirin-trading`, `kirincapital`
- Greenhouse: `kirintrading`, `kirincapital` (and `kirin` = 0 in the probe)
- Lever: `kirin`, `kirintrading`

## Recommended checker
```yaml
- key: kirin
  name: Kirin
  adapter: ashby
  settings: {board: kirin}
  careers_url: https://jobs.ashbyhq.com/kirin
  # group board (Italic, Sudo, Family, Courtly, Blemish, Kati, Kirin); trading roles appear under department "Kirin"
```

## Evidence
- Sample: `discovery/samples/kirin.json` (raw posting-API response).
- Capture: `discovery/captures/kirin/` (hosted page and its GraphQL response with org data). Playwright render of kirin.com: no content. Web: Built In NYC company and jobs pages, Simplify listing.
