"""Every checker replayed offline from its recorded fixture (tests/fixtures/cassettes/<company>.json.gz).

A fixture is recorded with `internwatch record <company>` (or `verify --record`) and stores the exact
responses of one live run plus the job count it produced. Replaying must give the same jobs.
"""
from pathlib import Path

import pytest

from internwatch.adapters import get_checker
from internwatch.adapters.base import FetchContext, dedupe
from internwatch.http import Cassette, Http

from conftest import REPO

CASSETTES = sorted((REPO / "tests" / "fixtures" / "cassettes").glob("*.json.gz"))


@pytest.mark.parametrize("path", CASSETTES, ids=[p.name.split(".")[0] for p in CASSETTES])
def test_replay_matches_recording(path: Path):
    cas = Cassette.load(path)
    meta = cas.meta
    checker = get_checker(meta["checker"])
    http = Http(replay=cas)
    jobs = dedupe(checker.fetch(http, meta["settings"] or {}, FetchContext()))
    assert len(jobs) == meta["count"]
    ids = {j.id for j in jobs}
    assert set(meta.get("ids_sample", [])) <= ids
    for j in jobs:
        assert j.id and j.title, f"job without id/title: {j}"
        assert j.url.startswith("http"), f"job {j.id} has no link: {j.url!r}"
    for jid in meta.get("detail_ids", []):
        j = next(j for j in jobs if j.id == jid)
        checker.detail(http, meta["settings"] or {}, j)


def test_fixtures_exist():
    assert CASSETTES, "no recorded fixtures: run `internwatch record`"
