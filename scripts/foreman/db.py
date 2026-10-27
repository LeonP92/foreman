"""Copy a database file so a branch server never touches the original."""

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

SQLITE_HEADER = b"SQLite format 3\x00"


def copy(src: Path, dst: Path) -> dict:
    with src.open("rb") as f:
        is_sqlite = f.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    if is_sqlite:
        # The backup API reads through SQLite, so WAL pages and live writers are seen consistently.
        with closing(sqlite3.connect(src)) as source, closing(sqlite3.connect(dst)) as target:
            source.backup(target)
        method = "sqlite-backup"
    else:
        shutil.copy2(src, dst)
        method = "file-copy"
    return {"method": method, "bytes": dst.stat().st_size}
