# GM Financial (`gm-financial`)

**Status:** verified   ·   **Checked:** 2026-10-27 (US Central)

General Motors' captive-finance subsidiary hires on its own Oracle Recruiting Cloud site, separate from GM's Workday
(`general-motors`). Found by the October 2026 audit: 28 US Summer 2027 internships open (Software Development
Engineer, Data Engineer, Data Science, Cybersecurity, Oracle Application Developer, …) in Dallas–Fort Worth.

- Feed: `GET https://fa-exvu-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions`,
  `siteNumber=CX_1` (the same shared `oracle` adapter as Akamai's CX_1).
- TotalJobsCount 128 = 128 read on 2026-10-27; 29 student roles, 20 matching the filters.
