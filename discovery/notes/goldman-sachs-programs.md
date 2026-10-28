# Goldman Sachs Programs (`goldman-sachs-programs`)

**Status:** verified   ·   **Checked:** 2026-10-27 (US Central)

The Possibilities Series (first-years) and Emerging Leaders Series (sophomores) are never Higher roles: their
applications are Avature project pages on recruiting360.avature.net, whose robots.txt ends `Disallow: /`. Their
program pages on goldmansachs.com (listed in `/feeds/programs-and-internships.json`; robots allows `/careers/`) are
server-rendered and say:

    APPLICATION DETAILS  Applications are now closed.  ELIGIBILITY  … graduating between December 2028 - June 2029  LOCATION …

The `program_pages` checker returns a program only while its APPLICATION DETAILS no longer say "Applications are now
closed". The job id is the page plus a hash of the ELIGIBILITY text, which shifts every round (graduation years),
so a new round is a new job and an edited deadline is not. A page without the heading marks the poll degraded.
Both pages were closed on 2026-10-27 (Emerging Leaders closed Oct 4; Possibilities expected ~Feb 2027).
