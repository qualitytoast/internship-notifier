# Booking.com (`booking`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://jobs.booking.com/booking/jobs. `jobs.booking.com/` and `/jobs` redirect there. |
| Hiring system | **iCIMS Jibe** tenant `workingatbooking`, over **iCIMS** with 2 portals: `external-workingatbooking.icims.com` (Booking.com, 89) and `careers-holdings-workingatbooking.icims.com` (Booking Holdings, 42). The same tenant serves **two career sites**: <br>• **Booking.com**: https://jobs.booking.com/booking/jobs, 89 jobs <br>• **Booking Holdings Center of Excellence**: https://www.bookingholdings-coe.com/bookingholdings-coe/jobs, 42 jobs |
| Recommended adapter | shared **`jibe`** (spec in `docusign.md`), settings `{host: jobs.booking.com}`, with **no `tags1`**, so both sites are covered (131) |

## What the page sends
- The `/booking/jobs` page calls `GET /api/jobs?page=1&sortBy=relevance&descending=false&internal=false&tags1=Booking.com%20Company%20Hierarchy%7CTransport%20Company%20Hierarchy%7CBooking%20Holdings%20Company%20Hierarchy`. `|` means OR, and the call returns `totalCount` **89**, all with `brand` "Booking.com".
  - It also calls `GET /api/jobs?featured=true&tags1=Booking%20Holdings%20COE%20Company%20Hierarchy`, which returns 7 featured COE jobs for a carousel.
- The COE site calls `GET https://www.bookingholdings-coe.com/api/jobs?…&tags1=Booking%20Holdings%20COE%20Company%20Hierarchy`, which returns `totalCount` **42**.
- **Omitting `tags1`** returns **131** = 89 + 42. That is every job of the tenant: `brand` Booking.com 89 plus Booking Holdings 42, with no overlap and no other brands. Agoda, KAYAK, OpenTable and Priceline are not in this tenant.
- `tags1` facet values: `Booking.com Company Hierarchy` 82, `Booking Holdings COE Company Hierarchy` 42, `Booking Holdings Company Hierarchy` 4, `Transport Company Hierarchy` 3.

## Recommended feed
- `GET https://jobs.booking.com/api/jobs?page=<N>&limit=100&internal=false` with N = 1, 2 (100 + 31). robots.txt has `crawl-delay: 5`.
- Keep `brand` on each job, so emails can say "Booking.com" or "Booking Holdings (COE)".
- If only Booking.com is wanted, add the page's `tags1=Booking.com Company Hierarchy|Transport Company Hierarchy|Booking Holdings Company Hierarchy`. I recommend tracking all 131 and filtering on `brand` in our code instead.

## Field map
Same as the jibe spec in `docusign.md`. Booking specifics:

| Job field | Path | Notes |
|---|---|---|
| id | `slug` = `req_id` (e.g. `30330`) | 131 unique |
| url | `meta_data.canonical_url` | Brand-correct: `https://jobs.booking.com/booking/jobs/{slug}?lang=en-us` (Booking.com) or `https://www.bookingholdings-coe.com/bookingholdings-coe/jobs/{slug}?lang=en-us` (COE). `https://jobs.booking.com/jobs/{slug}?lang=en-us` also works for both brands; it redirects to `/booking/jobs/{slug}`. |
| company | `brand` / `hiring_organization` | `Booking.com` / `Booking Holdings` |
| employment type | `employment_type` | `FULL_TIME` 123, `CONTRACTOR` 2, `PART_TIME` 1, null 5. **The internships are marked FULL_TIME**, so use the title. |
| department | `categories[].name` | Finance 28, Engineering 20, Business Development & Support 12, `Graduate` 1, … |

## Totals (observed 2026-10-20 00:14–00:17 UTC)
- **Feed, no filters:** **131**. 2 pages, 131 unique; the Booking.com subset is 89 and the COE subset is 42.
- **Live careers pages, no filters:**
  - Booking.com: a Playwright render of https://jobs.booking.com/booking/jobs showed "89 Results" and "of 89".
  - Booking Holdings COE: a Playwright render of https://www.bookingholdings-coe.com/bookingholdings-coe/jobs showed "42 Results" and "1 – 10 of 42".
  - Together: **131**.
- **Intern/student:** **4**, all Booking.com in Amsterdam:
  - 30330 "Junior Software Engineer I - Summer Internship 2027 (Amsterdam)"
  - 30463 "Finance internship: Financial Planning & Analysis (FP&A)"
  - 30464 "Finance internship: Accounting"
  - 30465 "Finance internship: Innovation & Process Design"

  There are no US internships. Most jobs are in the Netherlands (62), India (26) and Romania (16). There are 4 US jobs.
- Not part of this tenant: the Booking Holdings corporate site https://www.bookingholdings.com/careers/careers/ lists 20 more jobs, all US/UK corporate staff roles under `/careers-listing/<slug>/`. They come from a separate WordPress list, not Jibe. Plain httpx gets HTTP 403 (Cloudflare challenge), and only a browser render worked. I left them out: they are the parent company's corporate staff, not Booking.com.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://jobs.booking.com/api/jobs?page=1&limit=100&internal=false` | ALLOW | `Allow: /` (crawl-delay: 5) |
| `https://jobs.booking.com/booking/jobs`, `/jobs/<id>?lang=en-us` | ALLOW | `Allow: /` |
| `https://www.bookingholdings-coe.com/bookingholdings-coe/jobs` | ALLOW | `Allow: /` |

## Anti-bot / quirks
- jobs.booking.com has no challenge, and plain httpx works.
- `/sitemap.xml` is an empty `<urlset>`, so it is no use as a cross-check.
- The page fires `account.booking.com/privacy-consents/implicit` and snowplow analytics. Ignore them.

## Recommended checker
```yaml
- key: booking
  name: Booking.com
  adapter: jibe
  careers_url: https://jobs.booking.com/booking/jobs
  settings:
    host: jobs.booking.com           # no tags1: Booking.com (89) + Booking Holdings COE (42)
    use_employment_type: false       # internships are FULL_TIME here
    company_field: brand             # "Booking.com" | "Booking Holdings"
```

## Evidence
- Sample: `discovery/samples/booking.json` is the raw body of the `/booking/jobs` page's own call (with its `tags1` Booking.com filter): 10 jobs, totalCount 89, 162 KB.
- Capture: `discovery/captures/booking/` (bookmark `keywords=intern`, 4 results).
- Requests:
  - jobs.booking.com: 9 (2 probe calls, 2 pages, sitemap, `/`, `/jobs`, 2 job URLs).
  - www.bookingholdings-coe.com: 1. www.bookingholdings.com: 1 (403).
  - 3 Playwright renders.
  - All at ≥5 s per request on Jibe hosts.
