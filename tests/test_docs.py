import re
from pathlib import Path

from foreman import smells
from foreman.render import DIAGRAM_SMELLS

ROOT = Path(__file__).resolve().parent.parent


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_readme_commands_match_skills():
    documented = set(re.findall(r"`/foreman:(\w+)`", read("README.md")))
    assert documented == {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}


def test_smell_catalogue_names_every_threshold_and_kind():
    text = read("docs/smells.md")
    missing = [k for k in [*smells.THRESHOLDS, *DIAGRAM_SMELLS] if k not in text]
    assert not missing
