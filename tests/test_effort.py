"""AC4: rule matching and rules-file validation."""

from pathlib import Path

import pytest

from treadmill.effort import RulesError, load_rules

DEFAULTS = Path(__file__).parents[1] / "config" / "categories.toml"


@pytest.fixture
def rules():
    return load_rules(DEFAULTS)


def test_default_weights(rules):
    assert rules.weights == {"none": 0, "low": 1, "medium": 2, "high": 3}


@pytest.mark.parametrize(
    "app, title, expected",
    [
        ("Microsoft Edge", "Some talk - YouTube", "none"),
        ("Microsoft Edge", "Claude", "medium"),
        ("Microsoft Edge", "ChatGPT", "medium"),
        ("Microsoft Edge", "Inbox - Superhuman", "low"),
        ("Microsoft Edge", "Wikipedia", "none"),  # no title match → general browsing (D20)
        ("Claude", "", "medium"),
        ("Superhuman", "Inbox", "low"),
        ("Code", "api.py - treadmill", "high"),
        ("DaVinci Resolve", "", "high"),
        ("Finder", "Downloads", "none"),
        ("Notion", "Notes", "unrated"),  # unknown app
    ],
)
def test_defaults(rules, app, title, expected):
    assert rules.categorize(app, title) == expected


def test_title_match_ignores_case(rules):
    assert rules.categorize("Microsoft Edge", "my VIDEO - youtube") == "none"
    assert rules.categorize("Microsoft Edge", "chatgpt") == "medium"


def test_first_match_wins(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text(
        """
[weights]
none = 0
low = 1
medium = 2
high = 3
[[rules]]
app = "X"
title_contains = ["a"]
category = "high"
[[rules]]
app = "X"
category = "low"
"""
    )
    rules = load_rules(p)
    assert rules.categorize("X", "has a") == "high"
    assert rules.categorize("X", "zzz") == "low"


def test_title_rule_does_not_match_other_apps(rules):
    # "Claude" in a VS Code title must not make it medium
    assert rules.categorize("Code", "Claude Code") == "high"


@pytest.mark.parametrize(
    "body, message",
    [
        ("not [valid", "not valid TOML"),
        ("[weights]\nnone = 0\n", "[weights] must define"),
        (
            "[weights]\nnone=0\nlow=1\nmedium=2\nhigh=3\n[[rules]]\napp='X'\ncategory='huge'\n",
            "rule 1: unknown category 'huge'",
        ),
        ("[weights]\nnone=0\nlow=1\nmedium=2\nhigh=3\n[[rules]]\ncategory='low'\n", "rule 1: missing 'app'"),
    ],
)
def test_invalid_file_names_problem(tmp_path, body, message):
    p = tmp_path / "r.toml"
    p.write_text(body)
    with pytest.raises(RulesError, match=message.replace("[", r"\[")):
        load_rules(p)
