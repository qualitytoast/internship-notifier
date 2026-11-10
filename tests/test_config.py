"""config/companies.yaml is valid: every active company has a registered checker, its settings, and a fixture."""
import pytest

from internwatch import config as configmod
from internwatch.adapters import get_checker
from internwatch.report import fixture_path

from conftest import REPO

CFG = configmod.load(REPO)
REQUIRED = {
    "greenhouse": [("board", "boards")], "lever": ["site"], "ashby": [("board", "boards")], "workable": ["account"],
    "gem": ["board"], "pinpoint": ["subdomain"], "workday": ["host", "tenant", ("site", "sites")],
    "eightfold": ["host", "domain"], "oracle": ["host", "site"], "phenom": ["base_url", "ref_num"],
    "icims": ["portal"], "avature": ["list_url"], "applicantpro": ["subdomain", "domain_id"],
}


def test_keys_unique_and_names_present():
    keys = [c.key for c in CFG.companies]
    assert len(keys) == len(set(keys))
    assert all(c.name and c.careers_url for c in CFG.companies)


@pytest.mark.parametrize("c", CFG.active, ids=[c.key for c in CFG.active])
def test_active_company_is_runnable(c):
    get_checker(c.checker)
    for req in REQUIRED.get(c.checker, []):
        options = req if isinstance(req, tuple) else (req,)
        assert any(o in (c.settings or {}) for o in options), f"{c.key}: missing setting {req}"


@pytest.mark.parametrize("c", CFG.active, ids=[c.key for c in CFG.active])
def test_active_company_has_fixture(c):
    assert fixture_path(CFG, c.key).exists(), f"no recorded fixture for {c.key}: run `internwatch record {c.key}`"


def test_blocked_companies_explain_themselves():
    for c in CFG.companies:
        if c.status == "blocked":
            assert c.blocked_reason and c.fallback, f"{c.key}: blocked companies need blocked_reason and fallback"


def test_discovery_rebuilds_companies_yaml_exactly():
    """discovery/build_config.py regenerates config/companies.yaml byte for byte, so a rerun can never drop a company,
    a setting or a note made since (Bloomberg's second_order and the Citadel Securities programs once were)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_config", REPO / "discovery" / "build_config.py")
    build_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_config)
    text, missing = build_config.build()
    assert missing == []
    assert text == (REPO / "config" / "companies.yaml").read_text()


@pytest.mark.parametrize("c", CFG.active, ids=[c.key for c in CFG.active])
def test_fixture_was_recorded_with_the_current_settings(c):
    """A fixture recorded with older settings replays them, so the tests would no longer read what a run reads."""
    from internwatch.http import Cassette
    meta = Cassette.load(fixture_path(CFG, c.key)).meta
    assert (meta.get("checker"), meta.get("settings")) == (c.checker, c.settings), f"run `internwatch record {c.key}`"
