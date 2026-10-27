import json
import tomllib
from pathlib import Path

PLUGIN_MANIFESTS = [
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_versions_match_everywhere():
    versions = {p: load(p)["version"] for p in PLUGIN_MANIFESTS}
    versions["pyproject.toml"] = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    assert set(versions.values()) == {"0.1.0"}, versions


def test_marketplaces_have_required_fields():
    claude = load(".claude-plugin/marketplace.json")
    assert {"name", "owner", "plugins"} <= claude.keys()
    codex = load(".agents/plugins/marketplace.json")
    entry = codex["plugins"][0]
    assert (
        codex["name"] == "foreman" and {"installation", "authentication"} <= entry["policy"].keys()
    )
    assert entry["category"] and entry["source"]["url"].endswith("/foreman.git")
