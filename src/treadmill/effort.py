"""Effort categories: load the rules file and match app activity (spec §3)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("none", "low", "medium", "high")
UNRATED = "unrated"


class RulesError(ValueError):
    """The rules file is missing or invalid; the message names the problem."""


@dataclass(frozen=True)
class Rule:
    apps: tuple[str, ...]
    titles: tuple[str, ...]  # lowercased; empty means any title
    category: str


@dataclass(frozen=True)
class Rules:
    weights: dict[str, float]
    rules: tuple[Rule, ...]

    def categorize(self, app: str, title: str) -> str:
        """Return the first matching rule's category, or UNRATED."""
        lowered = title.lower()
        for rule in self.rules:
            if app not in rule.apps:
                continue
            if rule.titles and not any(t in lowered for t in rule.titles):
                continue
            return rule.category
        return UNRATED


def _str_list(value, where: str) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise RulesError(f"{where} must be a string or a non-empty list of strings")
    return tuple(value)


def load_rules(path: Path) -> Rules:
    try:
        raw = tomllib.loads(Path(path).read_text())
    except FileNotFoundError:
        raise RulesError(f"rules file not found: {path}")
    except tomllib.TOMLDecodeError as e:
        raise RulesError(f"rules file is not valid TOML: {e}")

    weights = raw.get("weights")
    if not isinstance(weights, dict) or set(weights) != set(CATEGORIES):
        raise RulesError(f"[weights] must define exactly: {', '.join(CATEGORIES)}")
    for name, w in weights.items():
        if not isinstance(w, (int, float)) or isinstance(w, bool):
            raise RulesError(f"weight for '{name}' must be a number")

    rules = []
    for i, r in enumerate(raw.get("rules", []), start=1):
        where = f"rule {i}"
        if not isinstance(r, dict):
            raise RulesError(f"{where} must be a table")
        if r.get("category") not in CATEGORIES:
            raise RulesError(
                f"{where}: unknown category {r.get('category')!r} (use {', '.join(CATEGORIES)})"
            )
        if "app" not in r:
            raise RulesError(f"{where}: missing 'app'")
        apps = _str_list(r["app"], f"{where}: 'app'")
        titles = ()
        if "title_contains" in r:
            titles = tuple(t.lower() for t in _str_list(r["title_contains"], f"{where}: 'title_contains'"))
        rules.append(Rule(apps, titles, r["category"]))

    return Rules({k: float(v) for k, v in weights.items()}, tuple(rules))
