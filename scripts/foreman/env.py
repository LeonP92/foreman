"""Run repo commands in a worktree's environment; read env files by name only; throwaway secrets."""

import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from foreman.config import DB_LOCATION_VARS

_DOTENV_LINE = re.compile(r"^(export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=[^\r\n]*", re.MULTILINE)
_ENV_FILE_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_]\w*)=([^\r\n]*)", re.MULTILINE)
_MAIN_CHECKOUT_VARS = ("VIRTUAL_ENV", "PYTHONPATH", "NODE_PATH")
THROWAWAY_LOCK_WAIT = 10


@contextmanager
def lock(path: Path, wait: float):
    """Hold an O_EXCL lock file next to shared state; give up after `wait` seconds."""
    deadline = time.monotonic() + wait
    while True:
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise OSError(
                    f"{path.as_posix()} held for {wait:g} s; delete it if no other run is using it"
                ) from None
            time.sleep(0.1)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def dotenv(path: Path, pairs: list[str]) -> dict:
    """List the names an env file sets, after rewriting the NAME=value lines given; never values."""
    with path.open(encoding="utf-8", newline="") as f:
        text = f.read()
    if pairs:
        values = dict(pair.split("=", 1) for pair in pairs)
        text = _DOTENV_LINE.sub(
            lambda m: f"{m[1] or ''}{m[2]}={values[m[2]]}" if m[2] in values else m[0], text
        )
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write(text)
    names = sorted({m[2] for m in _DOTENV_LINE.finditer(text)})
    return {"names": names, "database_locations": [n for n in names if n in DB_LOCATION_VARS]}


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))  # Windows: slashes and case


def environment(settings: dict, values: dict, env_files: list[Path]) -> dict:
    remove = {*DB_LOCATION_VARS, *settings["remove"]}
    checkout = _norm(settings["checkout"])

    def inside(value: str) -> bool:
        return _norm(value) == checkout or _norm(value).startswith(checkout.rstrip(os.sep) + os.sep)

    base = {
        k: v
        for k, v in os.environ.items()
        if k not in remove and k not in _MAIN_CHECKOUT_VARS and not inside(v)
    }
    # PATH often starts with the checkout's own tool folder (an activated venv): keep the rest.
    base["PATH"] = os.pathsep.join(
        p for p in os.environ.get("PATH", "").split(os.pathsep) if not inside(p)
    )
    for path in env_files:
        for name, value in _ENV_FILE_LINE.findall(path.read_text(encoding="utf-8")):
            if name in remove:
                raise ValueError(f"{path.as_posix()} sets {name}, a removed database location")
            base[name] = value

    def lookup(m: re.Match) -> str:
        if m[1] not in base:
            raise ValueError(f"${{{m[1]}}} is not set, or names a removed database location")
        return base[m[1]]

    return {**base, **{k: re.sub(r"\$\{(\w+)\}", lookup, v) for k, v in values.items()}}


def launch(settings_path: Path, cwd: Path, log: str, command: str, env_files: list[Path]) -> dict:
    """Run a repo command and wait (log "-"), or start a server in its own process group."""
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    env = environment(settings, settings["command" if log == "-" else "server"], env_files)
    # shell=True is deliberate: the commands are shell commands written by the repo.
    if log == "-":
        return {
            "returncode": subprocess.run(
                command, check=False, shell=True, cwd=cwd, env=env
            ).returncode
        }
    group = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with Path(log).open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **group,
        )
    return {"pid": proc.pid}


def throwaway(repo: Path, names: list[str]) -> dict:
    """The repo's private secrets file; add a random value for each missing name."""
    repo = repo.resolve()
    home = os.environ.get("APPDATA") if os.name == "nt" else os.environ.get("XDG_CONFIG_HOME")
    digest = hashlib.sha256(repo.as_posix().encode("utf-8")).hexdigest()[:8]
    path = (
        Path(home or Path.home() / ".config") / "foreman" / "secrets" / f"{repo.name}-{digest}.env"
    )
    added = []
    if names:
        path.parent.mkdir(parents=True, exist_ok=True)
        with lock(path.with_suffix(".lock"), THROWAWAY_LOCK_WAIT):
            # O_CREAT without O_TRUNC: made 0600 if missing, never overwritten
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "r+", encoding="utf-8") as f:
                have = set(re.findall(r"^([A-Za-z_]\w*)=", f.read(), re.MULTILINE))
                added = [n for n in dict.fromkeys(names) if n not in have]
                f.writelines(f"{n}={secrets.token_urlsafe(32)}\n" for n in added)
    return {"added": added, "path": path.as_posix()}
