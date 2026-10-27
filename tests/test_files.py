from foreman.files import language, list_files, read_text


def test_list_files_uses_git_and_respects_gitignore(make_repo):
    root = make_repo({"a.py": "", ".gitignore": "ignored/\n", "ignored/x.py": ""})
    assert list_files(root) == [".gitignore", "a.py"]


def test_list_files_skips_vendored_without_git(tmp_path):
    for p in ["src/a.py", "node_modules/m/i.js", "dist/b.js", ".venv/c.py"]:
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("", encoding="utf-8")
    assert list_files(tmp_path) == ["src/a.py"]


def test_ignore_globs_match_top_level_and_nested(make_repo):
    root = make_repo({"migrations/1.py": "", "app/migrations/2.py": "", "app/a.py": ""})
    assert list_files(root, ignore=["**/migrations/**"]) == ["app/a.py"]


def test_read_text_normalises_crlf_and_rejects_binary(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"a\r\nb\r\n")
    (tmp_path / "nul.bin").write_bytes(b"a\x00b")
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe\xfa")
    (tmp_path / "bom.py").write_bytes(b"\xef\xbb\xbfx = 1\n")
    assert read_text(tmp_path / "a.txt") == "a\nb\n"
    assert read_text(tmp_path / "nul.bin") is None
    assert read_text(tmp_path / "bad.txt") is None
    assert read_text(tmp_path / "bom.py") == "x = 1\n"


def test_language_by_extension():
    assert language("a/b.py") == "python"
    assert language("x.tsx") == "javascript"
    assert language("x.go") == "go"
    assert language("x.rs") is None
