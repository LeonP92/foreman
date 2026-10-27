"""Copy a database file so a branch server never touches the original."""

import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

SQLITE_HEADER = b"SQLite format 3\x00"


def _is_sqlite(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(len(SQLITE_HEADER)) == SQLITE_HEADER


def _read_only_uri(src: Path) -> str:
    with src.open("rb") as f:
        wal_mode = f.read(19)[18:] == b"\x02"
    # Even a read-only connection creates missing -wal/-shm files beside a WAL database. With no
    # -wal file no connection is open, so the file is complete and can be read as immutable.
    # An app that opens it and checkpoints mid-copy could tear the read; copy() checks for that.
    immutable = wal_mode and not src.with_name(src.name + "-wal").exists()
    return f"{src.resolve().as_uri()}?{'immutable=1' if immutable else 'mode=ro'}"


def _consistent(path: Path) -> bool:
    try:
        with closing(sqlite3.connect(path)) as con:
            return con.execute("pragma quick_check").fetchone() == ("ok",)
    except sqlite3.DatabaseError:  # badly torn pages fail to read at all
        return False


def copy(src: Path, dst: Path) -> dict:
    # A backup onto itself never finishes.
    if dst.exists() and os.path.samefile(src, dst):
        raise ValueError(f"{src.as_posix()} and {dst.as_posix()} are the same file")
    if _is_sqlite(src):
        if dst.exists() and not _is_sqlite(dst):
            raise ValueError(f"{dst.as_posix()}: exists and is not a SQLite database")
        # The backup API reads through SQLite, so WAL pages and live writers are seen consistently.
        # Read-only, so closing never checkpoints the source or deletes its -wal/-shm files.
        try:
            with (
                closing(sqlite3.connect(_read_only_uri(src), uri=True)) as source,
                closing(sqlite3.connect(dst)) as target,
            ):
                source.backup(target)
        except sqlite3.Error as exc:
            raise ValueError(f"{src.as_posix()} -> {dst.as_posix()}: {exc}") from None
        # catches a read torn by an app writing during an immutable read
        if not _consistent(dst):
            dst.unlink()
            raise ValueError(
                f"copy of {src.as_posix()} is inconsistent (the app may be writing) - stop it and retry"
            )
        method = "sqlite-backup"
    else:
        shutil.copy2(src, dst)
        method = "file-copy"
    return {"method": method, "bytes": dst.stat().st_size}
