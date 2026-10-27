# IBM (`ibm`)

**Status:** verified (2,216 = 2,216)   ·   **Checked:** 2026-10-26 (US Central)

| | |
|---|---|
| Official careers URL | https://www.ibm.com/careers/search |
| Hiring system | IBM's search service (`www-api.ibm.com/search/api/v2`, appId `careers`) feeds the search page; job pages are on careers.ibm.com (Avature, `JobDetail?jobId=<id>`). |
| Checker | custom `ibm` (`src/internwatch/checkers/ibm.py`) |

## Feed
- **Request:** `POST https://www-api.ibm.com/search/api/v2`, the body the page sends, with `size` 100 (the most the service
  allows; 500 answers 400), `from` 0, 100, …, and `_source` naming the page's exact field list (unknown names
  answer 400). There is no robots.txt.
- **Order:** the page sorts by `_score`, then `pageviews`, which tie on every hit (sort values `[0, 0]`), so its
  pages could repeat or skip jobs. `sort: [{"_id": "asc"}]` is accepted. On 2026-10-26 a walk of 23 requests read
  all 2,216 hits once, with 2,216 distinct ids.
- **careers.ibm.com** answers plain clients with an empty 202, so job pages are linked, not read.

## Field map (`hits.hits[]._source`)
| Job field | Path |
|---|---|
| id | the `jobId` in `url` |
| title | `title` |
| location | `field_keyword_19`: "City, CC" with an ISO 3166 country code, or "Multiple Cities" (49 internships) |
| employment type | `field_keyword_18`: Internship 246, Entry Level 129, Professional 1,841 |
| department | `field_keyword_08` (Consulting, Software Engineering, …) |
| workplace | `field_keyword_17` (Hybrid, Remote, blank) |
| snippet | `description` (a short excerpt) |

## Country codes
The location rules read a bare "City, DE" as Delaware, "City, IN" as Indiana, "City, CO" as Colorado and "City, ID"
as Idaho. The checker writes each code out as the country's name ("Ehningen, Germany"); a test checks that every
name it uses reads as that country. On 2026-10-26 this kept 14 student roles abroad (in Germany, Colombia, India,
…) from counting as US.

## Totals (2026-10-26)
- 2,216 jobs, 257 student roles, 163 matches: 125 in the US and 38 "Multiple Cities" (unsure, location?).
