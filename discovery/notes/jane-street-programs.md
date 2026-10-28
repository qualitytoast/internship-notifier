# Jane Street Programs (`jane-street-programs`)

**Status:** verified   ·   **Checked:** 2026-10-27 (US Central)

Jane Street's student programs (FTTP, FOCUS, INSIGHT, Bridge, SEE, AMP, WiSE, the Graduate Research Fellowship, …)
are not Greenhouse posts: each session is applied for through a janestreet.com form (`/apply-<session>`), so the
`jane-street` checker (Greenhouse board `janestreet`) never sees them. The programs-and-events page renders
`https://www.janestreet.com/jobs/programs-endpoint.json` (robots allows `/jobs/`):

- `[{name, location_filter, category_filter, sessions: [{id, office, dates, apply_page, deadline, formatted_deadline,
  preuniversity, availability_label, greenhouse_id, …}]}]`, 18 programs, 31 sessions on 2026-10-27.
- The file keeps past sessions (AMP 2026, Bridge NYC closed Sep 27, INSIGHT NYC closed Oct 25, IN FOCUS with a 2025
  deadline), events without a form (SF Happy Hour, SPiN, Women in STEM) and high-school programs (`preuniversity`).
- The checker returns a session only while it takes applications: an apply page and a deadline still ahead (11
  on 2026-10-27; in the US: FOCUS NYC by Nov 15, FTTP NYC by Jan 31, the Graduate Research Fellowship, Visiting
  Researcher). Session ids are reused every year (`fttp-nyc`), so the job id adds the deadline date.
- The `greenhouse_id`s in the file answer 404 on boards `janestreet` and `janestreetevents`.
