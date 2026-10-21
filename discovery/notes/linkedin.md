# LinkedIn — job feed discovery

**Status:** blocked
**Checked:** 2026-10-19 18:47–18:54 CDT. 19 requests in total: 12 through the polite helper (4 of them robots.txt) plus 7 robots.txt fetches by `discovery/robots_check.py`. **No www.linkedin.com page was requested.** Only its robots.txt was read, and the bookmark result below comes from the earlier Playwright capture.

**Why blocked:** LinkedIn posts its own openings only on www.linkedin.com: the company jobs tab, `/jobs/search`, `/jobs/view/<id>` and the `jobs-guest` API. For every user agent other than named search bots, that host's robots.txt is `User-agent: *` / `Disallow: /`, and its header says automated access is prohibited without LinkedIn's express permission. The allowed careers site (careers.linkedin.com) is a marketing site with no job data. Its "Search Jobs" and "Open roles" buttons only link to www.linkedin.com. The only allowed machine-readable feed named "linkedin", the Lever board, is a LinkedIn **partner sandbox of test postings**, not real jobs. No other official ATS or feed for LinkedIn's own jobs was found.

## Careers site
- Official careers URL: https://careers.linkedin.com/ (marketing pages only). The job search behind its "Search Jobs" nav button is https://www.linkedin.com/company/linkedin/jobs/, which robots.txt disallows.
- Hiring system: LinkedIn's own platform. Jobs are posted natively on linkedin.com/jobs under the "LinkedIn" page (company id 1337) and its affiliated pages, and candidates apply on LinkedIn.
  - careers.linkedin.com runs on Adobe Experience Manager as a Cloud Service. Evidence: `/etc.clientlibs/linkedin-experience-manager/...`, content root `/content/lem/careers/us/en`, assets on `delivery-p143253-e1476319.adobeaemcloud.com`, and `/lem/static/libs/granite/csrf/token.json` (returns 404). It sits behind Cloudflare and LinkedIn's edge (`x-li-fabric`, `x-li-pop` headers).
  - The captured page loaded no job data. Its XHRs were only the AEM CSRF token (404), `/li/track`, `litms` metadata, `microsites/api/lix-treatments`, `microsites/api/global-alerts` and Adobe Target/Analytics.
  - No Greenhouse, Lever, Workday, Eightfold, Phenom, iCIMS, Avature, SuccessFactors, SmartRecruiters or Jobvite signature appears in the careers pages. Web search found no external ATS host (Workday, Eightfold or Greenhouse) for LinkedIn's own hiring.
- Public job detail URL format: `https://www.linkedin.com/jobs/view/<jobId>/` (disallowed).

### Where every job link on careers.linkedin.com points
| Page (allowed) | Link text | Target (all robots **BLOCK**) |
|---|---|---|
| every page, nav | Search Jobs | `https://www.linkedin.com/company/linkedin/jobs/` |
| `/` and `/Locations/*` (Sunnyvale, Dublin, Chicago, Bangalore) | Open roles | `https://www.linkedin.com/jobs/search/?f_C=1337,9202023,2561065,2587638,290903,39939&geoId=<city>&sortBy=R` |
| `/pathways-programs/internships/Technical` | Search our current Engineering Internship opportunities | `https://www.linkedin.com/jobs/search/?currentJobId=3705752503&f_C=39939,9202023,2587638,1337&f_E=1&f_F=eng&geoId=92000000&sortBy=R` (`f_E=1` = Internship level, `f_F=eng` = Engineering, `geoId 92000000` = Worldwide) |
| `/pathways-programs/internships`, `/pathways-programs/entry-level` | (no job lists; "Apply today" points back to `/pathways-programs/entry-level`) | — |
| bookmark | — | `https://www.linkedin.com/jobs/search-results/?…&geoId=103644278&f_C=1337,2587638,39939&f_SAL=f_SA_id_226001:275001` (`geoId 103644278` = United States) |

## Recommended feed
**None.** Every route to LinkedIn's actual job list is disallowed. Candidates considered:

| Candidate | Verdict |
|---|---|
| `www.linkedin.com/company/linkedin/jobs/`, `/jobs/search/?f_C=…`, `/jobs/search-results/…`, `/jobs/view/<id>/` | robots BLOCK (`Disallow: /`). The capture of the bookmark also got `307 → HTTP 999 → /authwall` (sign-up wall). |
| `www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?f_C=1337…` (guest JSON/HTML API) | robots BLOCK (`Disallow: /`). The Googlebot group also disallows `/jobs-guest/`. Not used, and no workaround attempted. |
| careers.linkedin.com (robots.txt is 200 with an empty body, so everything is allowed) | Allowed, but holds no job data, only the deep links above. |
| `GET https://api.lever.co/v0/postings/linkedin?mode=json` | Allowed, but this is **"LinkedIn Partner Sandbox - RSC testing"** (the `jobs.lever.co/linkedin` page title; RSC = LinkedIn Recruiter System Connect). Its 23 postings are test data, e.g. "Anirban jobReq 3 - public", "RF_TEST_BUG_BASH_Lever", "sgupta13_test_job", "Deauth Test", "Truck Driver - Hawai", with teams like "Investment Banking" and "Voice and Character" and a salary of 100–200 AZN per month. **Do not use.** |
| `api.linkedin.com` (official REST APIs) | robots.txt returns 404, so robots allows it. But the API needs OAuth 2.0 and partner-program approval. LinkedIn's Job Posting API is write-only (for ATS partners to *push* jobs), and there is no public job-search read API. Not usable. |
| Microsoft careers (`apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=LinkedIn`), since LinkedIn is a Microsoft subsidiary | robots ALLOW (`Allow: /api/pcsx`). My one request got **HTTP 429** ("Please try again later") while the Microsoft discovery was using that host. I did not retry. There is no evidence that LinkedIn's jobs appear there: LinkedIn's careers site never links to Microsoft's. **Unverified.** |

## Field map
Not applicable: there is no allowed feed. For reference, the Lever sandbox has the standard Lever v0 shape: `id`, `text`, `categories.{location,team,commitment,department,allLocations}`, `createdAt` (epoch ms), `hostedUrl`, `applyUrl`, `descriptionPlain`, `workplaceType`, `country`, `salaryRange`.

## Totals (observed 2026-10-19)
| Measure | Value | How observed |
|---|---|---|
| Feed total, no filters | none | No allowed feed exists. |
| Live careers page total, no filters | not observable | The only list (`www.linkedin.com/company/linkedin/jobs/`) is robots-disallowed. The Playwright capture of the bookmark got HTTP 999 and the authwall, with no count shown. |
| Intern / student | unknown | Same reason. SimplifyJobs cross-check sources (Summer2027 `README.md` 1.13 MB and `README-Off-Season.md` 1.65 MB, fetched 18:53) contain **0** mentions of LinkedIn, so the cross-check gives no coverage today. |
| Lever "linkedin" board | 23 postings, all test data | `GET api.lever.co/v0/postings/linkedin?mode=json` (24.5 KB) |

### LinkedIn company IDs in LinkedIn's own job links
- The link sets differ. The bookmark uses {1337, 2587638, 39939}. The Technical-internships page uses {39939, 9202023, 2587638, 1337}. The location pages use {1337, 9202023, 2561065, 2587638, 290903, 39939}.
- **1337 = LinkedIn.** This is the page with slug `linkedin`, and LinkedIn's help center uses `linkedin.com/company/1337` as its example.
- **2587638 and 39939 were not identified.** About 20 web searches found nothing: the bare IDs, `urn:li:organization:<id>`, `linkedin.com/company/<id>`, `f_C=<id>` strings, `linkedin_id` fields, and each ID combined with candidate names. Search engines do not index numeric company IDs. The authoritative lookup, `www.linkedin.com/company/<id>`, is robots-disallowed, so I did not do it.
- Context:
  - LinkedIn's help center ("Affiliated LinkedIn Pages") says jobs from affiliated Pages can be shown on the parent Page. "See all jobs" on a parent Page therefore lists the parent plus its affiliates in `f_C`.
  - LinkedIn's own Pages playbook (business.linkedin.com PDF) shows the affiliated pages on LinkedIn's Page as Microsoft (the parent, id 1035, which is *not* in the list), LinkedIn China (领英中国) and Lynda.com (now LinkedIn Learning).
  - So 2587638, 39939, 9202023, 2561065 and 290903 are very likely LinkedIn's affiliated or subsidiary pages. Candidates are LinkedIn China, lynda.com/LinkedIn Learning, Glint, SlideShare and Drawbridge, but **which ID is which is unconfirmed**.

## robots.txt
| URL | Verdict | Rule (discovery/robots_check.py) |
|---|---|---|
| https://careers.linkedin.com/ | ALLOW | no matching rule (robots.txt 200, empty) |
| https://careers.linkedin.com/pathways-programs/internships | ALLOW | no matching rule |
| https://careers.linkedin.com/pathways-programs/internships/Technical | ALLOW | no matching rule |
| https://www.linkedin.com/company/linkedin/jobs/ | BLOCK | Disallow: / |
| https://www.linkedin.com/jobs/search/?f_C=1337%2C9202023%2C2561065%2C2587638%2C290903%2C39939&geoId=103644278&sortBy=R | BLOCK | Disallow: / |
| https://www.linkedin.com/jobs/search-results/?keywords=jobs&geoId=103644278&f_C=1337%2C2587638%2C39939&f_SAL=… (bookmark) | BLOCK | Disallow: / |
| https://www.linkedin.com/jobs/search/?currentJobId=3705752503&f_C=39939%2C9202023%2C2587638%2C1337&f_E=1&f_F=eng&geoId=92000000&sortBy=R | BLOCK | Disallow: / |
| https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?f_C=1337&start=0 | BLOCK | Disallow: / |
| https://www.linkedin.com/jobs/view/4444658212/ | BLOCK | Disallow: / |
| https://www.linkedin.com/company/39939, https://www.linkedin.com/company/2587638 | BLOCK | Disallow: / |
| https://api.linkedin.com/rest/jobs | ALLOW | no robots.txt (404), but OAuth/partner-only |
| https://api.lever.co/v0/postings/linkedin?mode=json | ALLOW | Allow: / (sandbox, not real jobs) |
| https://jobs.lever.co/linkedin | ALLOW | Allow: / |
| https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=LinkedIn&… | ALLOW | Allow: /api/pcsx |
| https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/README.md | ALLOW | no robots.txt |

## Anti-bot / gotchas
- The header of www.linkedin.com/robots.txt says: "The use of robots or other automated means to access LinkedIn without the express permission of LinkedIn is strictly prohibited". Permission requests go to whitelist-crawl@linkedin.com. Named crawlers (LinkedInBot, Googlebot and others) have their own groups, and `*` gets `Disallow: /`.
- The Playwright capture of the bookmark shows heavy bot defence:
  - `/jobs/search-results` redirects (307) to `/jobs/search`, which returns **HTTP 999** and then the `/authwall` sign-up page.
  - HUMAN/PerimeterX loads (`li.protechts.net`, app `PXdOjV695v`, the URL carries `uc=scraping`), along with reCAPTCHA Enterprise and Azure WAF beacons (`ps.azurewaf.microsoft.com`).
- careers.linkedin.com: Cloudflare, no challenge seen. Responses carry `ETag` and `Last-Modified`.
- Lever slug collision: the token `linkedin` exists on Lever but belongs to LinkedIn's partner sandbox. A naive ATS probe reports "23 jobs", which is a false positive.

## Recommended checker approach
1. Mark LinkedIn **blocked** in config and coverage, with the reason above.
   - Do not poll any www.linkedin.com URL, including the guest API, RSS-like endpoints or mirrors.
   - Keep LinkedIn out of the zero-jobs and drop health alerts.
2. Do **not** add the Lever `linkedin` board. Add it to a deny-list so automatic ATS probing does not "discover" it again.
3. Coverage fallback (no scraping):
   - The SimplifyJobs cross-check already runs, but it lists 0 LinkedIn roles today.
   - The user can create a LinkedIn job alert inside their own account for `f_C=1337,9202023,2561065,2587638,290903,39939` with `f_E=1` (Internship) and US or Canada `geoId`s. LinkedIn would then email new postings, which the user could forward or label.
   - Alternatively, ask for permission at whitelist-crawl@linkedin.com.
4. If permission is ever granted, the source to watch would be `www.linkedin.com/jobs/search/?f_C=1337,9202023,2561065,2587638,290903,39939&f_E=1&geoId=<US 103644278 | Canada 101174742>&sortBy=DD`. Detail pages are `/jobs/view/<id>/`.
5. careers.linkedin.com is allowed but not worth polling: it has no postings, and its internship deep link only changes when someone edits the page.

## Sample
`discovery/samples/linkedin.json` (12 KB) contains:
- the job deep links found on the allowed careers.linkedin.com pages, each with its robots verdict;
- a trimmed copy of `GET https://api.lever.co/v0/postings/linkedin?mode=json`: board title, all 23 test titles, a one-line summary per posting, and the first two raw postings.
