# Chan Zuckerberg Initiative (`chan-zuckerberg`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://chanzuckerberg.com/careers/career-opportunities/ (the bookmark without its stray `?`). The page says: "Explore our current openings below. Additionally, there are career opportunities available with our **science** and **education** teams". Those two words link to https://www.biohub.org/ and https://learningcommons.org/, whose careers pages are https://biohub.org/careers/ and https://learningcommons.org/careers/. |
| Hiring system | Greenhouse, **three boards**: `chanzuckerberginitiative` (CZI "Central", 7), `biohub` (Biohub, the science org, 12), `education` (Learning Commons, 5). Every job link on the three pages points to `job-boards.greenhouse.io/<board>/jobs/<id>`. |
| Recommended adapter | shared `greenhouse` adapter with `boards: [chanzuckerberginitiative, biohub, education]` |

The probe's 7 on `chanzuckerberginitiative` is correct for CZI itself. It looked low because CZI's science and education hiring moved to separate boards.

## Recommended feed
- **Requests:** `GET https://boards-api.greenhouse.io/v1/boards/{chanzuckerberginitiative,biohub,education}/jobs`
- **Pagination:** none. `meta.total` matches the job count on each board.
- **Fields:** standard Greenhouse list (see notes/walleye.md). `company_name` is `Chan Zuckerberg Initiative` / `Biohub` / `Learning Commons`. `absolute_url` is `https://job-boards.greenhouse.io/<board>/jobs/<id>`.

## Totals (observed 2026-10-19)
- **Feed, no filters:** 7 + 12 + 5 = **24** postings (24 unique ids). Biohub posts 3 requisitions twice, at two locations: R1642 Research Scientist, AI; R1644 Research Engineer, AI; R1710 Staff Research Scientist, AI Safety.
- **Live pages, no filters (Playwright):**
  - chanzuckerberg.com/careers/career-opportunities/ lists **7** jobs in 6 team groups, with 7 Greenhouse links that are exactly the feed ids.
  - biohub.org/careers/ shows "**12** results", with 12 `.../biohub/jobs/<id>` links equal to the feed.
  - learningcommons.org/careers/ shows "**5** OPEN ROLES", with 5 `.../education/jobs/<id>` links equal to the feed.
- **Intern/student:** **0**. The CZI Internship Program page (/careers/internship-program/) describes 10–12-week summer internships but lists no openings. When open, they would appear on these boards.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/{chanzuckerberginitiative,biohub,education}/jobs | ALLOW | no matching rule |
| https://chanzuckerberg.com/careers/career-opportunities/ | ALLOW | no matching rule |
| https://biohub.org/careers/ · https://learningcommons.org/careers/ | ALLOW | no matching rule |

## Anti-bot / quirks
- None seen. The board token `education` is generic, so check it by `company_name` = "Learning Commons" if it ever changes.

## Recommended checker
```yaml
- key: chan-zuckerberg
  name: Chan Zuckerberg Initiative
  adapter: greenhouse
  settings:
    boards: [chanzuckerberginitiative, biohub, education]
  careers_url: https://chanzuckerberg.com/careers/career-opportunities/
```

## Evidence
- Sample: `discovery/samples/chan-zuckerberg.json` is the raw `biohub` board list (12 jobs, 13 KB).
- Capture: `discovery/captures/chan-zuckerberg/`. I made Playwright renders of the CZI, Biohub, Learning Commons and Internship Program pages, plus one GET per board.
