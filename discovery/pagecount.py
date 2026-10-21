"""Render careers pages in headless Chromium and print the job-count texts they show:
    .venv/bin/python discovery/pagecount.py URL [URL ...]
Used to compare a checker's job count with what the live careers page displays (filters off)."""
import re
import sys

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
COUNT = re.compile(r"[^.\n]{0,40}(?:\b\d[\d,]*\+?\s+(?:jobs?|results?|positions?|openings?|roles?|opportunities|matches)\b"
                   r"|\bof\s+\d[\d,]*\s+in total\b|\b(?:positions?|jobs?|openings?|roles?)\s*:\s*\d[\d,]*)[^.\n]{0,30}", re.I)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    for url in sys.argv[1:]:
        page = b.new_page(user_agent=UA)
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2500)
            text = page.inner_text("body")
            hits = list(dict.fromkeys(m.group(0).strip() for m in COUNT.finditer(text)))[:6]
            print(f"{url}\n   {hits or 'no count text found'}")
        except Exception as e:  # noqa: BLE001
            print(f"{url}\n   failed: {type(e).__name__}: {str(e)[:150]}")
        page.close()
    b.close()
