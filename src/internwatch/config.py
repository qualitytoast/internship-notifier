"""Load settings.yaml, companies.yaml, filters.yaml and the .env secrets."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .filters import Rules, kw_regex, load_rules

ROOT = Path(os.environ.get("INTERNWATCH_HOME", Path(__file__).resolve().parents[2]))
PLACEHOLDER_RE = re.compile(r"^<.*>$")


@dataclass
class Company:
    key: str
    name: str
    category: str
    careers_url: list[str]
    checker: str
    settings: dict = field(default_factory=dict)
    locations: list[str] | None = None
    aliases: list[str] = field(default_factory=list)
    status: str = "active"          # active | blocked | disabled
    blocked_reason: str = ""
    fallback: str = ""
    role_keywords: list[str] = field(default_factory=list)
    big: bool = False               # very large site: quick (newest-first) scans, full scan every full_scan_hours
    notes: str = ""
    timeout_minutes: float | None = None   # time budget for one check (default: schedule.check_timeout_minutes)
    full_scan_hours: float | None = None   # big sites: hours between full scans (default: schedule.full_scan_hours)
    verified: dict = field(default_factory=dict)  # discovery evidence (informational)

    @property
    def extra_role_re(self):
        return kw_regex(self.role_keywords) if self.role_keywords else None

    @property
    def all_names(self) -> list[str]:
        return [self.name] + self.aliases


@dataclass
class Settings:
    raw: dict
    root: Path

    def __getitem__(self, k):
        return self.raw[k]

    def get(self, *path, default=None):
        cur = self.raw
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def path(self, *keys: str) -> Path:
        p = Path(self.get("paths", *keys))
        return p if p.is_absolute() else self.root / p

    @property
    def recipient(self) -> str:
        return str(self.get("email", "to", default="")).strip()


@dataclass
class Secrets:
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    healthchecks_url: str = ""

    @property
    def email_ready(self) -> bool:
        return all(v and not PLACEHOLDER_RE.match(v) for v in (self.smtp_user, self.smtp_password))

    @property
    def healthchecks_ready(self) -> bool:
        return bool(self.healthchecks_url) and not PLACEHOLDER_RE.match(self.healthchecks_url)


@dataclass
class Config:
    settings: Settings
    companies: list[Company]
    rules: Rules
    secrets: Secrets
    root: Path

    def company(self, key_or_name: str) -> Company:
        k = key_or_name.strip().lower()
        for c in self.companies:
            if c.key == k or c.name.lower() == k:
                return c
        raise KeyError(f"unknown company '{key_or_name}' (see config/companies.yaml)")

    @property
    def active(self) -> list[Company]:
        return [c for c in self.companies if c.status == "active"]


KNOWN_KEYS = {"key", "name", "category", "careers_url", "checker", "settings", "locations", "aliases", "status",
              "blocked_reason", "fallback", "role_keywords", "big", "notes", "timeout_minutes", "full_scan_hours",
              "verified"}


def load_companies(path: Path) -> list[Company]:
    data = yaml.safe_load(path.read_text()) or {}
    out, seen = [], set()
    for i, raw in enumerate(data.get("companies", []) or []):
        where = f"{path.name} entry #{i + 1} ({raw.get('key', '?') if isinstance(raw, dict) else raw!r})"
        if not isinstance(raw, dict) or not raw.get("key") or not raw.get("name") or not raw.get("checker"):
            raise ValueError(f"{where}: every company needs key, name and checker")
        unknown = set(raw) - KNOWN_KEYS
        if unknown:
            raise ValueError(f"{where}: unknown field(s) {', '.join(sorted(unknown))} (typo?)")
        urls = raw.get("careers_url") or []
        if isinstance(urls, str):
            urls = [urls]
        verified = raw.get("verified") or {}
        c = Company(
            key=str(raw["key"]), name=str(raw["name"]), category=raw.get("category", ""), careers_url=urls,
            checker=raw["checker"], settings=raw.get("settings") or {}, locations=raw.get("locations"),
            aliases=raw.get("aliases") or [], status=raw.get("status", "active"),
            blocked_reason=raw.get("blocked_reason", ""), fallback=raw.get("fallback", ""),
            role_keywords=raw.get("role_keywords") or [], big=bool(raw.get("big", False)), notes=raw.get("notes", ""),
            timeout_minutes=raw.get("timeout_minutes"), full_scan_hours=raw.get("full_scan_hours"),
            verified=verified if isinstance(verified, dict) else {"note": str(verified)},
        )
        if c.status not in ("active", "blocked", "disabled"):
            raise ValueError(f"{where}: status must be active, blocked or disabled")
        if c.key in seen:
            raise ValueError(f"duplicate company key {c.key} in {path}")
        seen.add(c.key)
        out.append(c)
    return out


def load(root: Path | None = None) -> Config:
    root = Path(root or ROOT)
    load_dotenv(root / ".env", override=False)
    settings = Settings(yaml.safe_load((root / "config" / "settings.yaml").read_text()), root)
    companies = load_companies(root / "config" / "companies.yaml")
    rules = load_rules(str(root / "config" / "filters.yaml"))
    secrets = Secrets(
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587") or 587),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        email_from=os.environ.get("EMAIL_FROM", "") or os.environ.get("SMTP_USER", ""),
        healthchecks_url=os.environ.get("HEALTHCHECKS_PING_URL", ""),
    )
    return Config(settings, companies, rules, secrets, root)
