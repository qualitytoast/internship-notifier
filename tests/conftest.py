"""Shared fixtures. Every test runs offline: network access is replaced by recorded fixtures or fakes."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from internwatch.config import Company, Config, Secrets, Settings
from internwatch.db import DB, iso
from internwatch.filters import load_rules
from internwatch.health import Outcome
from internwatch.models import Job

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    """The suite must pass offline: any real connection attempt fails the test. Tests marked `chrome` talk to their
    own servers on 127.0.0.1 and run only when asked for (INTERNWATCH_CHROME_TESTS=1)."""
    if request.node.get_closest_marker("chrome"):
        return
    import socket

    def refuse(*a, **kw):
        raise RuntimeError("network access in a test (tests must run offline from fixtures)")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def no_chrome(monkeypatch, request):
    """No test starts a real Chrome by accident (a Workday request with the real settings would): starting one fails
    with BrowserUnavailable, naming the cause. Tests marked `chrome` start it on purpose."""
    if request.node.get_closest_marker("chrome"):
        return
    from internwatch import chrome_session

    async def refuse(self):
        raise RuntimeError("a test tried to start a real Chrome")
    monkeypatch.setattr(chrome_session.ChromeSession, "_launch", refuse)


@pytest.fixture
def rules():
    return load_rules(str(REPO / "config" / "filters.yaml"))


@pytest.fixture
def make_cfg(tmp_path, rules):
    """Config backed by the real settings.yaml/filters.yaml, with every path inside tmp_path."""
    def _make(companies: list[Company], **overrides) -> Config:
        raw = yaml.safe_load((REPO / "config" / "settings.yaml").read_text())
        raw["paths"] = {k: str(tmp_path / Path(v).name) for k, v in raw["paths"].items()}
        raw["email"]["to"] = "me@example.com"
        for section, values in overrides.items():
            raw.setdefault(section, {}).update(values)
        return Config(Settings(raw, tmp_path), companies, rules, Secrets(), tmp_path)
    return _make


def company(key: str, checker: str = "fake", **kw) -> Company:
    return Company(key=key, name=kw.pop("name", key.title()), category=kw.pop("category", "software"),
                   careers_url=[f"https://{key}.example.com/careers"], checker=checker, **kw)


def job(jid: str, title: str, location: str = "New York, NY", **kw) -> Job:
    return Job(id=jid, title=title, location=location, url=f"https://jobs.example.com/{jid}", **kw)


class FakeChecker:
    """Stands in for run_checker: returns scripted results per company, call after call."""

    def __init__(self, script: dict):
        self.script = script
        self.calls: dict[str, int] = {}

    def __call__(self, cfg, c, *, mode="full", known=(), state=None, gate=None, record=None, replay=None,
                 detail_limit=0, deadline=None):
        i = self.calls.get(c.key, 0)
        self.calls[c.key] = i + 1
        steps = self.script[c.key]
        res = steps[min(i, len(steps) - 1)]
        o = Outcome(company=c, mode=mode, started_at=iso(), state={})
        if isinstance(res, Exception):
            o.error_kind, o.error = getattr(res, "kind", "error"), str(res)
        else:
            o.jobs = list(res)
        return o


@pytest.fixture
def memdb():
    db = DB(":memory:")
    yield db
    db.close()
