"""Print a compact per-company view of the Playwright captures: python discovery/summarize.py [key ...]"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IGNORE_SIGS = {"radancy", "beamery", "cornerstone"}


def main(keys):
    for d in sorted((ROOT / "captures").iterdir()):
        if keys and d.name not in keys:
            continue
        p = d / "summary.json"
        if not p.exists():
            print(f"### {d.name}: (no capture)")
            continue
        s = json.loads(p.read_text())
        for i, pg in enumerate(s["pages"]):
            print(f"### {d.name} [{i}] status={pg.get('status')} title={pg.get('title', '')[:70]!r}")
            print(f"    final: {pg.get('final_url', '')[:200]}")
            if pg.get("error"):
                print(f"    ERROR: {pg['error'][:200]}")
            sigs = {k: v for k, v in pg.get("signatures", {}).items()}
            for k, v in sigs.items():
                print(f"    sig {k}: {', '.join(x[:110] for x in v[:4])}")
            for f in pg.get("feeds", [])[:5]:
                post = f" body={f['post'][:160]!r}" if f.get("post") else ""
                print(f"    feed {f['method']} {f['url'][:190]} items={f['items']} path={f['path']} totals={f['totals']}{post}")
            if pg.get("count_texts"):
                print(f"    counts: {pg['count_texts'][:5]}")
            if not pg.get("feeds"):
                xhr = [x for x in pg.get("xhr", []) if "GET 307" not in x][:12]
                for x in xhr:
                    print(f"    xhr {x[:200]}")


if __name__ == "__main__":
    main(sys.argv[1:])
