# IMC Trading (`imc`)

**Status:** verified-feed (Greenhouse is a superset of the site; difference explained)   ·   **Checked:** 2026-10-20 (00:20–00:35 UTC)

| | |
|---|---|
| Official careers URL | https://www.imc.com/eu/search-careers. Its default Location is "All": "Showing 10 of **160** jobs". The regional pages pre-filter by office: `/us/search-careers` defaults to "Chicago, New York" (54), `/ap/search-careers` to "Seoul, Sydney" (35), `/in/search-careers` to "Mumbai" (17). The bookmark `https://www.imc.com/us/careers/jobs` is a 404. Job pages are `https://www.imc.com/us/careers/jobs/<greenhouse id>` (+ `/apply`). |
| Hiring system | Greenhouse board **`imc`**. The site is Next.js, server-rendered from a CMS copy of the board (the RSC payload carries a `greenhouseData` document, and job links use the Greenhouse ids). |
| Recommended adapter | shared `greenhouse`, `{board: imc}` |

## Recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/imc/jobs` (242 KB, no pagination, `meta.total` 171).
- **Useful metadata** (in the list response):
  - `Worker Sub Type`: Experienced 126, **Intern 17**, Graduate 15, **Working Student 2**, Program Event 2, Temporary 1, none 8.
  - `Career Site Locale`: us 56, eu 44, au 39, in 17, none 15.
  - `Job Category`.
  - `Is Hidden Job?`: true 2, false 18, null 151.
  - The shared adapter's `_employment_type()` looks for metadata names containing "employment type", "job type", "worker type", "position type" or "time type". **"Worker Sub Type" is not matched.** Today every intern/student posting also says Intern/Student in its title, so nothing is lost, but adding `worker sub type` to that list would make the type available.

## Field map
Standard Greenhouse list fields:
- `id`, `title`, `absolute_url` (`https://job-boards.greenhouse.io/imc/jobs/<id>`; the site's own page is `https://www.imc.com/us/careers/jobs/<id>`), `first_published`.
- `location.name`: "Chicago, United States", "Amsterdam, Netherlands", "Sydney,  Australia" (double space), multi-office strings joined with "; ".

## Totals (observed 2026-10-20)
- **Feed, no filters:** **171**.
- **Live careers page, no filters:** **160**. A Playwright render of `/eu/search-careers` with Location "All" showed "Showing 10 of 160 jobs".
- **Why 11 fewer:** the site leaves out non-job postings and flagged postings. 9 Greenhouse ids are absent from the page payload:
  - 8 postings with no `Worker Sub Type`, i.e. talent pools, events and interest forms: "2027 EU Campus Programme Talent Community", "2027 EU Chess Academy - Expression of Interest", "2027 US Chess Academy Interest Form", "Aarhus Networking event | IMC Trading", "EU Campus - Aarhus Hackahton IMCity", "PACT 2026", "Prosperity 2026 - Role Interest Form", "US PhD Talent Community".
  - " Commodities Trader - China" (Sydney).

  2 more are in the payload but flagged `Is Hidden Job? = true`: "Connect with us at ICLR 2026!" and one "Graduate Quantitative Researcher" (Amsterdam). 171 − 9 − 2 = 160. Greenhouse is complete, so keep all 171; filtering drops the event/talent postings anyway.
- **Intern/student:** **19** (17 `Intern` + 2 `Working Student`; the title regex also gives 19). **8** are in the US:
  - Quantitative Trader Intern – Summer 2027, Software Engineer Intern – Summer 2027, Quant Performance Engineer Intern – Summer 2027 (Chicago)
  - Quantitative Research Intern (BS/MS) and (PhD) – Summer 2027 (Chicago)
  - Machine Learning Engineer Intern – Summer 2027, Deep Learning Research Intern – Summer 2027 – New York, Hardware Machine Learning PhD Research Internship (New York)

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/imc/jobs | ALLOW | no matching rule |
| https://www.imc.com/eu/search-careers | ALLOW | `Allow: /` |
| https://www.imc.com/us/search-careers | ALLOW | `Allow: /` |

## Anti-bot / quirks
- No bot protection seen on www.imc.com in Playwright renders.
- The site's location filter is a custom dropdown, and the default is region-specific. Record careers_url as the `/eu/` page, because that is the one that shows all locations by default.

## Recommended checker
```yaml
- key: imc
  name: IMC Trading
  adapter: greenhouse
  settings: {board: imc}
  careers_url: https://www.imc.com/eu/search-careers
  # optional: job_url https://www.imc.com/us/careers/jobs/{id}; metadata "Worker Sub Type" = Intern / Working Student
```

## Evidence
- Sample: `discovery/samples/imc.json` (raw Greenhouse list with metadata, compact JSON).
- Playwright: /us/ (default and dropdown attempts), /eu/, /ap/ and /in/ search pages.
