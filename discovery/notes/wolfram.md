# Wolfram (`wolfram`)

**Status:** needs-custom   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://www.wolfram.com/company/careers/opportunities/ (the bookmark). The careers nav also has a Students page (https://www.wolfram.com/company/careers/students/). It describes internships and programmes and links back to "View current openings" on the same opportunities page. |
| Hiring system | **Recruiterbox** (now Trakstar Hire), client id **42716**. The page loads the widget from `w.recruiterbox.com/static/client-src-served/widget/42716/rbox_api.js` / `rbox_impl.js` and fetches the list with one XHR to `app.recruiterbox.com/widget/42716/openings/`. There is no Greenhouse, Lever or Ashby board: the probe's `greenhouse wolfram` returned 0. |
| Recommended adapter | small custom checker `custom:recruiterbox`. It is one GET of a JSON array. If more Recruiterbox clients turn up, it would fit a shared `recruiterbox` adapter with `{widget_id}`. |

## Recommended feed
- **Request:** `GET https://app.recruiterbox.com/widget/42716/openings/`
- **Headers:** a normal browser UA and `Accept: application/json`. No cookies, auth, or query parameters. The page sends none either.
- **Response:** a bare JSON **array** with one object per opening. There is no envelope, no total, and no paging. Today it returns 7 objects (93 KB, because each object carries the full HTML description and the application form schema).
- **Pagination:** none. Every opening comes back in one response.
- **Detail endpoint:** not needed. `description` already holds the full HTML.

## Field map
Paths are relative to each array element.

| Job field | Response path | Notes |
|---|---|---|
| id | `id` (int, e.g. 704703) | Unique and stable. `hash_id` (`fk0zicw`) and `job_code` (`wlfr0331`) also exist. |
| title | `title` | Some titles have a trailing space (`Wolfram Student Ambassador Initiative `), so trim. The location is often inside the title after an em dash (`…—Oxfordshire, UK`). |
| location(s) | `location.city`, `location.state`, `location.country` | Fields can be null, e.g. `{"city":"Remote","state":null,"country":null}`. Remote flags: `allows_remote` (bool) and `remote_options` (`fully_remote` / `hybrid` / `partially_remote` / `does_not_allow_remote`). |
| url (detail/apply) | built: `https://www.wolfram.com/company/careers/opportunities/#op-{id}-{slug}` | `slug` follows the widget's `sluggify(title)`: lowercase, delete every `-`, replace each run of whitespace with `-`, then delete everything outside `[a-z0-9-]`. That gives e.g. `#op-614419-senior-applications-engineer-data-science--machine-learninglinkping-sweden`. The widget reads only the id (`#op-704703` alone opened the right detail in Playwright), so a wrong slug is harmless. |
| posted date | none | There is no created or published field. Use first-seen. `close_date` exists but is null today. |
| description / snippet | `description` | HTML. |
| employment type | `position_type` | `"Full-time"` or `""` |
| department / team | `team` | `Career Opportunities` (jobs) or `Programs` (Winter School, Student Ambassador, …) |
| other | `company_name` ("Wolfram"), `application_fields[]` (form schema), `application_acknowledgement_enabled` | |

## Totals (observed 2026-10-19)
- **Feed, no filters:** **7**. There are 5 under `team: Career Opportunities` and 2 under `Programs`.
- **Live careers page, no filters:** **7**. In a Playwright render, the widget listed 5 under "Career Opportunities" and 2 under "Programs". It had 7 `#op-<id>-<slug>` anchors, and their ids are exactly the feed ids.
- **Intern/student:** **1** by our rules: "Wolfram Student Ambassador Initiative" (Champaign IL, partially remote, team Programs). It is a student ambassador programme, not an internship. "2027 Wolfram Winter School" (remote, January 2027) is an educational programme, and our rules do not match it. The Students page says that "Wolfram has internships available throughout the year". They are posted in this same widget when open (none today).

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://app.recruiterbox.com/widget/42716/openings/ | ALLOW | `Allow: /`. The only disallow is `/prepare*`. |
| https://w.recruiterbox.com/static/client-src-served/widget/42716/rbox_impl.js | ALLOW | `Allow: /` |
| https://www.wolfram.com/company/careers/opportunities/ | ALLOW | no matching rule |

## Anti-bot / quirks
- I saw no bot protection. The widget talks to `app.recruiterbox.com` through an easyXDM iframe, but the openings URL works as a plain GET.
- There is no total field, so the health check should alert on an empty array or a 4xx/5xx. Wolfram always has at least the Programs entries.
- Recruiterbox was rebranded as Trakstar Hire. If the widget host changes, the page's XHR is the source of truth.

## Recommended checker
```yaml
- key: wolfram
  name: Wolfram
  adapter: custom:recruiterbox
  careers_url: https://www.wolfram.com/company/careers/opportunities/
  settings:
    list_url: https://app.recruiterbox.com/widget/42716/openings/   # GET, JSON array, no paging
    id: id
    title: title                     # strip()
    location: [location.city, location.state, location.country]   # skip nulls; add "Remote" when allows_remote
    employment_type: position_type
    department: team
    description: description         # HTML
    job_url: "https://www.wolfram.com/company/careers/opportunities/#op-{id}-{slug}"
    slug: "title.lower().replace('-', '') -> re.sub(r'\\s+', '-') -> re.sub(r'[^a-z0-9-]', '')"
  health:
    expect_nonempty: true
```

## Evidence
- Sample: `discovery/samples/wolfram.json` is the raw openings response (7 openings, 93 KB).
- Capture: `discovery/captures/wolfram/` has the same XHR. I also did Playwright renders of the opportunities page, the Students page, and the `#op-704703` deep link (its title was "2027 Wolfram Winter School - Wolfram"). I made one plain GET of the feed and one fetch of `rbox_impl.js` to read `sluggify`/`extractOidFromStr`.
