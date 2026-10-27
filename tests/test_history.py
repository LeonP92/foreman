import shutil

from foreman.history import analyse


def test_cochange_pairs_and_conf(make_repo):
    root = make_repo(
        {"x": ""}, commits=[{"a.py": "1", "b.py": "1"}, {"a.py": "2", "b.py": "2"}, {"a.py": "3"}]
    )
    h = analyse(root)
    assert h["churn"]["a.py"] == 3
    assert h["pairs"][0] == {"a": "a.py", "b": "b.py", "both": 2, "conf": 1.0}


def test_bulk_commits_excluded(make_repo):
    bulk = {f"f{i}.py": "1" for i in range(31)}
    root = make_repo({"x": ""}, commits=[bulk, {"f0.py": "2"}])
    h = analyse(root)
    assert h["churn"] == {"f0.py": 1, "x": 1} and h["pairs"] == []


def test_ignore_filters_paths(make_repo):
    c = [{"a.py": "1", "g.lock": "1"}, {"a.py": "2", "g.lock": "2"}]
    h = analyse(make_repo({"x": ""}, commits=c), ["*.lock"])
    assert "g.lock" not in h["churn"] and h["pairs"] == []


def test_paths_with_spaces_and_unicode(make_repo):
    c = [{"docs/my file.md": "1", "src/café.py": "1"}, {"docs/my file.md": "2", "src/café.py": "2"}]
    h = analyse(make_repo({"x": ""}, commits=c))
    assert h["pairs"][0]["a"] == "docs/my file.md" and h["pairs"][0]["b"] == "src/café.py"


def test_no_repo_returns_note(tmp_path):
    h = analyse(tmp_path)
    assert h["churn"] == {} and h["pairs"] == [] and h["note"]


def test_missing_git_binary_returns_note(monkeypatch, make_repo):
    root = make_repo({"x": ""})
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    h = analyse(root)
    assert h["churn"] == {} and h["pairs"] == [] and h["note"]
