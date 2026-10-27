import sqlite3
from contextlib import closing

import pytest
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
