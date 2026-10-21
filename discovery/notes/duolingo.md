# Duolingo (`duolingo`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://careers.duolingo.com/ (job list at `#careers`). The bookmarks `?type=Thrive%20Program#careers` and `?type=Intern#careers` are client-side filters on this one list. |
| Hiring system | **Greenhouse** board `duolingo`. The React app (main.*.js) loads `https://boards-api.greenhouse.io/v1/boards/duolingo/departments` and builds the whole job list from it. **Breezy** (`duolingo.breezy.hr`) is a separate board for **freelance/contract** roles, linked only by the "View freelance jobs" button. |
| Recommended adapter | shared `greenhouse` adapter, `board: duolingo`. This is sufficient. Breezy is optional (`custom:breezy`, spec below). |

## What the "type" filter is (Intern / Thrive Program)
The app computes a type for each Greenhouse job from the custom field **`Req Type`** (`jobs[].metadata[name="Req Type"].value`):

| Req Type value | careers.duolingo.com type |
|---|---|
| `University - Graduating Intern` | **Intern** |
| `University - Thrive Intern` | **Thrive Program** |
| `University - New Grad` | New Grad |
| anything else (`Industry`) | Industry |

So the **Thrive Program lives on Greenhouse**, not Breezy. Today no job has `University - Thrive Intern`, which is why the Thrive bookmark is empty. The title rules still catch Thrive titles ("thrive program" is in filters.yaml). The checker could also map `Req Type` to employment_type to be safe: the adapter reads metadata names containing "employment type" / "job type" etc., and **not** "Req Type".

## What Breezy holds, and whether to track it
- `GET https://duolingo.breezy.hr/json` returns a JSON array of **3** positions, all `type.name: "Contract"`:
  - Country Marketing Manager, Nigeria (Contractor)
  - Performance Marketing Program Manager (Contract), New York
  - Producer, Gaming Partnerships (Contract), Southeast Asia
- The careers page preloads that URL, but its freelance loader is stubbed. In main.js: `My = async () => Promise.resolve([])`, used as `Iy(My, {key: "freelanceJobs@1.0.0"})`. So Breezy jobs **never appear** in the careers.duolingo.com list, and the type menu has no "Freelance" entry. The page only links out to https://duolingo.breezy.hr ("View freelance jobs"), and that page lists the same 3 (Playwright).
- **Conclusion:** Greenhouse alone covers everything on careers.duolingo.com, including the Intern and Thrive types. Breezy is a separate contractor board with no student roles. Track it only for whole-company coverage. If you do, here is the spec:

  `custom:breezy`. Request: `GET https://duolingo.breezy.hr/json`. This is a public JSON array (no paging, no total).

  | Job field | Path |
  |---|---|
  | id | `id` (e.g. `4ab15c2e5b05`) |
  | title | `name` (the site strips a trailing ` (Contract)` / ` (Contractor)`) |
  | location | `location.name`, plus `locations[].name`, `location.is_remote` |
  | url | `url` (`https://duolingo.breezy.hr/p/<friendly_id>`) |
  | posted | `published_date` (ISO) |
  | employment type | `type.name` (`Contract`) |
  | department | `department` |

## Recommended feed (Greenhouse)
- `GET https://boards-api.greenhouse.io/v1/boards/duolingo/jobs`. This gives the same 63 jobs as the page's `/departments` call. `meta.total` is 63, and there is no pagination.
- `absolute_url` is `https://careers.duolingo.com/jobs/<id>?gh_jid=<id>`.
- Other metadata: `Division`, `Featured Title`, `Featured City Name`. `location.name` uses `;` between cities ("New York, NY; Pittsburgh, PA").

## Totals (observed 2026-10-19)
- **Feed, no filters:** Greenhouse **63**, plus Breezy 3, which is optional and not counted in the result JSON.
- **Live careers page, no filters:** **63**. Playwright on careers.duolingo.com showed 5 "Featured jobs". After clicking "VIEW ALL JOBS" it showed the full list grouped by department: 63 links `careers.duolingo.com/jobs/<id>`, exactly the feed ids. duolingo.breezy.hr lists 3.
- **Intern/student:** **4**, all `Req Type: University - Graduating Intern`:
  - Data Scientist, Intern (NY/Pittsburgh)
  - Data Scientist, Intern (PhD) (NY/Pittsburgh)
  - Illustrator, Intern (Detroit)
  - Product Manager, MBA Intern (Pittsburgh)

  Thrive Program: 0.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/duolingo/jobs | ALLOW | no matching rule |
| https://careers.duolingo.com/ | ALLOW | no robots.txt |
| https://duolingo.breezy.hr/json · https://duolingo.breezy.hr/ | ALLOW | no matching rule (only /css, /fonts, /stylesheets, /javascripts are disallowed) |

## Anti-bot / quirks
- No bot protection. The SPA renders nothing until its web fonts load (`document.fonts.check`). A headless render that blocks fonts shows an empty page, which explains the empty earlier capture.
- The page caches jobs in localStorage (`jobs@1.1.0`). That doesn't matter for the API checker.

## Recommended checker
```yaml
- key: duolingo
  name: Duolingo
  adapter: greenhouse
  settings:
    board: duolingo
    employment_type_field: "Req Type"   # optional: 'University - Graduating Intern' / 'University - Thrive Intern'
  careers_url: https://careers.duolingo.com/
# optional, freelance contracts only:
# - key: duolingo-freelance
#   adapter: custom:breezy
#   settings: {url: https://duolingo.breezy.hr/json}
```

## Evidence
- Sample: `discovery/samples/duolingo.json` is the raw Breezy `/json` response (3 positions). The Greenhouse list is standard.
- Capture: `discovery/captures/duolingo/` (both bookmarks; the page body was empty because fonts were blocked). I made Playwright renders with fonts allowed (featured view and "View all jobs") and of duolingo.breezy.hr. I fetched main.d59926e631cd9729d57c.js once to read the type mapping and the stubbed freelance loader.
