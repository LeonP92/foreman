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


def copy(src: Path, dst: Path) -> dict:
    # A backup onto itself never finishes.
    if dst.exists() and os.path.samefile(src, dst):
        raise ValueError(f"{src.as_posix()} and {dst.as_posix()} are the same file")
    if _is_sqlite(src):
        if dst.exists() and not _is_sqlite(dst):
            raise ValueError(f"{dst.as_posix()}: exists and is not a SQLite database")
        # The backup API reads through SQLite, so WAL pages and live writers are seen consistently.
        try:
            with closing(sqlite3.connect(src)) as source, closing(sqlite3.connect(dst)) as target:
                source.backup(target)
        except sqlite3.Error as exc:
            raise ValueError(f"{src.as_posix()} -> {dst.as_posix()}: {exc}") from None
        method = "sqlite-backup"
    else:
        shutil.copy2(src, dst)
        method = "file-copy"
    return {"method": method, "bytes": dst.stat().st_size}
