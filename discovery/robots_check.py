"""Evaluate robots.txt for specific feed URLs: python discovery/robots_check.py URL [URL ...]"""
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from internwatch.http import ssl_context  # noqa: E402
from internwatch.robots import from_response  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
CACHE = Path(__file__).resolve().parent / "robots"
CACHE.mkdir(exist_ok=True)


def main(urls):
    seen = {}
    with httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True, verify=ssl_context()) as c:
        for url in urls:
            p = urlsplit(url)
            host = f"{p.scheme}://{p.netloc}"
            if host not in seen:
                try:
                    r = c.get(host + "/robots.txt")
                    status, text = r.status_code, r.text
                except httpx.HTTPError as e:
                    status, text = None, str(e)
                (CACHE / f"{p.netloc}.txt").write_text(f"# status {status}\n{text}")
                seen[host] = from_response(status, text)
            rules = seen[host]
            ok = rules.allowed(url)
            print(f"{'ALLOW' if ok else 'BLOCK'}  {url[:150]}\n       -> {rules.matching_rule(url)}")


if __name__ == "__main__":
    main(sys.argv[1:])
