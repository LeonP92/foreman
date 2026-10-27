import sqlite3
from contextlib import closing

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
