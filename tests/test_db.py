import os
import shutil
import sqlite3
from contextlib import closing

import pytest
from foreman import db
from foreman.cli import main
from foreman.db import copy


def test_sqlite_copy_includes_uncheckpointed_wal_writes(tmp_path):
    src = tmp_path / "a.db"
    con = sqlite3.connect(src)
    con.execute("pragma journal_mode=wal")
    con.execute("create table t(x)")
    con.execute("insert into t values (1)")
    con.commit()  # still open, so the write sits in the WAL
    assert copy(src, tmp_path / "b.db")["method"] == "sqlite-backup"
    with closing(sqlite3.connect(tmp_path / "b.db")) as out:
        assert out.execute("select count(*) from t").fetchone() == (1,)
    con.close()


def test_other_files_are_copied_byte_for_byte(tmp_path, capsys):
    src = tmp_path / "data.bin"
    src.write_bytes(b"not a database")
    assert main(["db-copy", str(src), str(tmp_path / "out.bin")]) == 0
    assert '"method": "file-copy"' in capsys.readouterr().out
    assert (tmp_path / "out.bin").read_bytes() == b"not a database"


def _db(path, value):
    with closing(sqlite3.connect(path)) as con:
        con.execute("create table t(x)")
        con.execute("insert into t values (?)", (value,))
        con.commit()


def test_copy_onto_itself_is_refused(tmp_path):
    _db(tmp_path / "a.db", 1)
    with pytest.raises(ValueError, match="same file"):
        copy(tmp_path / "a.db", tmp_path / "a.db")


def test_existing_sqlite_dst_is_replaced(tmp_path):
    _db(tmp_path / "a.db", 1)
    _db(tmp_path / "b.db", 2)
    copy(tmp_path / "a.db", tmp_path / "b.db")
    with closing(sqlite3.connect(tmp_path / "b.db")) as out:
        assert out.execute("select x from t").fetchall() == [(1,)]


def test_existing_non_sqlite_dst_is_refused(tmp_path):
    _db(tmp_path / "a.db", 1)
    (tmp_path / "notes.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(ValueError, match="not a SQLite database"):
        copy(tmp_path / "a.db", tmp_path / "notes.txt")
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_missing_dst_parent_is_a_one_line_error(tmp_path, capsys):
    _db(tmp_path / "a.db", 1)
    assert main(["db-copy", str(tmp_path / "a.db"), str(tmp_path / "no" / "b.db")]) == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "unable to open database file" in err


def _sidecars(src):
    return {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in src.parent.glob(src.name + "*")
    }


def test_wal_source_files_are_left_alone(tmp_path):
    src = tmp_path / "a.db"
    with closing(sqlite3.connect(src)) as writer:
        writer.execute("pragma journal_mode=wal")
        writer.execute("create table t(x)")
        writer.commit()
        before = _sidecars(src)
        assert before.keys() == {"a.db", "a.db-wal", "a.db-shm"}
        for name in before:  # left behind by an app that died
            shutil.copy2(tmp_path / name, tmp_path / name.replace("a.db", "orphan.db"))
        copy(src, tmp_path / "b.db")
        assert _sidecars(src) == before
    orphan = tmp_path / "orphan.db"
    sizes = {name: size for name, (size, _) in _sidecars(orphan).items()}
    copy(orphan, tmp_path / "c.db")
    # the last connection to close would checkpoint and delete them. Sizes only: a reader rebuilds
    # -shm, SQLite's scratch index, in place; the database and -wal are untouched.
    assert {name: size for name, (size, _) in _sidecars(orphan).items()} == sizes
    copy(src, tmp_path / "d.db")  # closed cleanly: no sidecars, and none created
    assert _sidecars(src).keys() == {"a.db"}


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory permissions")
def test_source_in_read_only_folder_is_copied(tmp_path):
    folder = tmp_path / "ro"
    folder.mkdir()
    with closing(sqlite3.connect(folder / "a.db")) as con:
        con.execute("pragma journal_mode=wal")
        con.execute("create table t(x)")
        con.execute("insert into t values (7)")
        con.commit()
    folder.chmod(0o555)
    try:
        copy(folder / "a.db", tmp_path / "b.db")
    finally:
        folder.chmod(0o755)
    with closing(sqlite3.connect(tmp_path / "b.db")) as out:
        assert out.execute("select x from t").fetchall() == [(7,)]


def test_inconsistent_copy_is_removed_and_refused(tmp_path, monkeypatch):
    _db(tmp_path / "a.db", 1)
    monkeypatch.setattr(db, "_consistent", lambda path: False)
    with pytest.raises(ValueError, match="inconsistent"):
        copy(tmp_path / "a.db", tmp_path / "b.db")
    assert not (tmp_path / "b.db").exists()
