# Epic Systems (`epic-systems`)

**Status:** needs-custom (Next.js page with the full job list in its RSC payload; the Avature portal is robots-blocked)   ·   **Checked:** 2026-10-19 (US Central) = 2026-10-20 00:15–00:17 UTC

| | |
|---|---|
| Official careers URL | https://careers.epic.com/jobs/. The bookmark `?q=aW50ZXJu` is base64 for "intern", a keyword-filtered view; track the unfiltered list. |
| Hiring system | **Avature** (`epic.avature.net`, portal `Careers`). Every "View details" link goes to `https://epic.avature.net/Careers/FolderDetail/{slug}/{id}`. The robots.txt of epic.avature.net **disallows `/Careers`**: only a list of other portals is allowed, and there is a final `Disallow: /`. So the checker must not fetch Avature. careers.epic.com (Next.js App Router, Turbopack) is the allowed front-end. |
| Recommended adapter | `custom:epic-careers`: one GET of the list page, decoding the RSC flight data. An optional cheap id check comes first (see below). |

## Recommended feed
- **Request (full list, titles):** `GET https://careers.epic.com/jobs/` returns about 270 KB of HTML, `text/html; charset=utf-8`. The SSR HTML says "Showing 0 positions" because the list is filled on the client. All the data is already in the page's React Server Components payload.
- **Decoding:**
  1. Concatenate the string argument of every `self.__next_f.push([1,"…"])` script. Each argument is a JSON string literal: use `json.loads` on it, then join. Today that is 3 pushes and 172,811 characters.
  2. In that text, find `"allOpenJobs":` and `json.JSONDecoder().raw_decode` the array that follows. It is `[{"id":"740"},{"id":"30318"},…]`, **41** entries, all open and published jobs in display order.
  3. Find `"avaturePositions":` and raw_decode the object that follows. It maps Avature id → `{externalName, shortSummary, background, isOpen, isPublished, referenceNumber}` for **479** positions, including closed and unpublished ones. Today 395 have `isOpen` and 41 have `isOpen && isPublished`.
  4. Jobs = `[avaturePositions[x.id] for x in allOpenJobs]`. The set {isOpen && isPublished} equals `allOpenJobs` exactly, which is a useful consistency check.
- **Cheap change check (optional):** `GET https://careers.epic.com/cached-api/jobs/search/?searchText=` (589 bytes, `text/plain` that holds JSON) returns `[{"id":"740"},…]`. These are the **same 41 ids in the same order** as `allOpenJobs`. Use it every poll and fetch `/jobs/` only when the id set changes. Keep the trailing slash: `/cached-api/jobs/search?…` 308-redirects to it. `searchText=intern` is a keyword search; do not use it.
- **Detail:** there is none on careers.epic.com. The Avature FolderDetail pages are robots-blocked, so put the link in emails but never fetch it. `shortSummary` and `background` are the only description text.
- **Headers:** a normal browser UA. No cookies.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `allOpenJobs[].id` (string) | the Avature position id, e.g. `30318` |
| title | `avaturePositions[id].externalName` | e.g. "Software Developer Intern - Summer 2027" |
| location(s) | not provided | Epic hires on its campus in **Verona, WI**. Use a default location of `Verona, WI, United States`. The cards show no location. |
| url (detail/apply) | built: `https://epic.avature.net/Careers/FolderDetail/{slug}/{id}` with `slug = re.sub(r'[^A-Za-z0-9]', '-', externalName)` (one dash per character, so " - " becomes `---`) | matched all 41 links on the rendered page, e.g. `Software-Developer-Intern---Summer-2027/30318` |
| posted date | not provided | first-seen time |
| description / snippet | `shortSummary` ("An internship that makes an impact.") + `background` ("Working towards a bachelor's degree in …") | |
| employment type | none | use the title |
| department / team | none in the payload | category landing pages exist (`/jobs/softwaredevelopment`, `/jobs/culinary`, `/jobs/intern`, …) but are not needed |
| other | `referenceNumber` | the display order inside a category |

## Totals (observed 2026-10-20 00:15–00:17 UTC)
- **Feed, no filters:** **41** (`allOpenJobs`), equal to the cached-api search with an empty query (41 ids, same order).
- **Live careers page, no filters:** **41**. A Playwright render of `https://careers.epic.com/jobs/` showed "**Showing 41 positions**" with 41 unique FolderDetail links (123 hrefs, 3 per card).
- **Intern/student:** **2**:
  - 30318 Software Developer Intern - Summer 2027
  - 1437 User Experience Design Intern

  The bookmark's keyword search "intern" showed "7 positions". That search matches description text as well as titles; only these 2 titles are internships.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://careers.epic.com/jobs/ | ALLOW | `Allow: /` (disallows only /admin/, /docs/, /cms/, /content-folder-proxy/) |
| https://careers.epic.com/cached-api/jobs/search/?searchText= | ALLOW | `Allow: /` |
| https://epic.avature.net/Careers/FolderDetail/Software-Developer-Intern---Summer-2027/30318 | **BLOCK** | `Disallow: /`. Only portals such as /talentCommunity, /OpenHouse, … are allowed; `Careers` is not. |
| https://epic.avature.net/Careers/SearchJobs | **BLOCK** | `Disallow: /` |

## Anti-bot / quirks
- No challenge on careers.epic.com (4 requests plus 1 Playwright render).
- The endpoint name `cached-api` suggests a server-side cache, so a new Avature job may appear here with some delay. I could not measure that delay; today its 41 ids matched the page exactly.
- Next.js build ids change on deploy. Do not hard-code `_rsc` tokens or chunk names. Parse the HTML's `self.__next_f.push` strings, which is stable across builds.
- If `allOpenJobs` or `avaturePositions` is missing, the site changed; alert. The id-only search endpoint still works as a fallback, but it has no titles.

## Recommended checker
```yaml
- key: epic-systems
  name: Epic Systems
  adapter: custom:epic-careers
  careers_url: https://careers.epic.com/jobs/
  settings:
    ids_url: https://careers.epic.com/cached-api/jobs/search/?searchText=   # JSON [{"id": "..."}]; poll this
    list_url: https://careers.epic.com/jobs/      # fetch when ids change; decode self.__next_f.push strings
    open_ids_key: allOpenJobs
    positions_key: avaturePositions              # id -> {externalName, shortSummary, background, isOpen, isPublished}
    job_url: "https://epic.avature.net/Careers/FolderDetail/{slug}/{id}"   # slug = re.sub('[^A-Za-z0-9]', '-', title); link only
    default_location: "Verona, WI, United States"
  health:
    expect: "len(allOpenJobs) == count(isOpen and isPublished)"
```

## Evidence
- Sample: `discovery/samples/epic-systems.html`, the raw `/jobs/` HTML (270 KB) with the `self.__next_f.push` payload holding `allOpenJobs` and `avaturePositions`.
- Capture: `discovery/captures/epic-systems/` (the bookmark render: "7 positions", the cached-api call with `searchText=intern`).
- Requests this run: 3 (robots, cached-api with an empty query, the `/jobs/` HTML) and 1 Playwright render.
