import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

RUN = Path(__file__).resolve().parents[1] / "scripts" / "run.py"


def _run(*args, env=None):
    return subprocess.run(
        [sys.executable, "-I", RUN, *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
    )


def _settings(tmp_path: Path, command: dict) -> Path:
    path = tmp_path / "s.json"
    data = {"remove": ["SHOP_DB"], "checkout": str(tmp_path / "main"), "command": command}
    path.write_text(json.dumps({**data, "server": {}}), encoding="utf-8")
    return path


def _show(code: str) -> str:
    return f'"{sys.executable}" -c "import os; {code}"'


def test_dotenv_lists_names_and_rewrites_lines(tmp_path):
    dotenv = tmp_path / ".env"
    # Bytes, so Windows text mode doesn't turn the CRLF fixture into CR CR LF.
    dotenv.write_bytes(b"SECRET_KEY=s3cret\r\nexport DATABASE_URL=sqlite:///real.db\r\n")
    listed = _run("dotenv", dotenv)
    assert json.loads(listed.stdout) == {
        "database_locations": ["DATABASE_URL"],
        "names": ["DATABASE_URL", "SECRET_KEY"],
    }
    assert "s3cret" not in listed.stdout
    rewritten = _run("dotenv", dotenv, "DATABASE_URL=sqlite:///copy.db")
    assert "copy.db" not in rewritten.stdout
    assert dotenv.read_bytes() == b"SECRET_KEY=s3cret\r\nexport DATABASE_URL=sqlite:///copy.db\r\n"


def test_launch_reads_references_after_removing_database_variables(tmp_path):
    env = {**os.environ, "SHOP_KEY": "k", "DATABASE_URL": "real", "SHOP_DB": "real"}
    show = _show(
        "print(os.environ.get('A'), 'DATABASE_URL' in os.environ, 'SHOP_DB' in os.environ)"
    )
    ran = _run("launch", _settings(tmp_path, {"A": "${SHOP_KEY}"}), tmp_path, "-", show, env=env)
    assert ran.stdout.split()[:3] == ["k", "False", "False"]
    assert json.loads(ran.stdout.split("\n", 1)[1]) == {"returncode": 0}
    for name in ["DATABASE_URL", "SHOP_DB"]:
        settings = _settings(tmp_path, {"A": f"${{{name}}}"})
        failed = _run("launch", settings, tmp_path, "-", show, env=env)
        assert failed.returncode == 1
        assert failed.stderr.strip().splitlines() == [
            f"foreman: ${{{name}}} is not set, or names a removed database location"
        ]


def test_launch_exits_with_the_command_status(tmp_path):
    ran = _run("launch", _settings(tmp_path, {}), tmp_path, "-", _show("os._exit(3)"))
    assert ran.returncode == 3
    assert json.loads(ran.stdout) == {"returncode": 3}


def test_launch_starts_a_server_and_prints_its_pid(tmp_path):
    log = tmp_path / "server.log"
    ran = _run("launch", _settings(tmp_path, {}), tmp_path, log, _show("print('up')"))
    pid = json.loads(ran.stdout)["pid"]
    assert isinstance(pid, int)
    for _ in range(100):
        if log.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.1)
    assert log.read_text(encoding="utf-8").strip() == "up"


def test_launch_loads_env_files_but_never_a_database_location(tmp_path):
    settings = _settings(tmp_path, {"A": "${SHOP_KEY}"})
    secrets_file = tmp_path / "shop.env"
    secrets_file.write_bytes(b"SHOP_KEY=from-file\r\n")
    show = _show("print(os.environ.get('A'))")
    env = {k: v for k, v in os.environ.items() if k != "SHOP_KEY"}
    ran = _run("launch", "--env-file", secrets_file, settings, tmp_path, "-", show, env=env)
    assert ran.stdout.split()[0] == "from-file"
    secrets_file.write_text("SHOP_KEY=k\nDATABASE_URL=sqlite:///real.db\n", encoding="utf-8")
    failed = _run("launch", "--env-file", secrets_file, settings, tmp_path, "-", show, env=env)
    assert failed.returncode == 1
    assert failed.stderr.strip().splitlines() == [
        f"foreman: {secrets_file.as_posix()} sets DATABASE_URL, a removed database location"
    ]
    assert "real.db" not in failed.stderr


def test_launch_drops_variables_pointing_into_the_main_checkout(tmp_path):
    main = tmp_path / "main"
    env = {
        **os.environ,
        "VIRTUAL_ENV": "/elsewhere/venv",
        "PYTHONPATH": "/elsewhere/lib",
        "NODE_PATH": "/elsewhere/node",
        "SHOP_CACHE": str(main / "cache"),
        "SHOP_DOTTED": f"{tmp_path}{os.sep}x{os.sep}..{os.sep}main{os.sep}.{os.sep}logs",
        "SHOP_NEIGHBOUR": str(tmp_path / "main-other"),
        "PATH": os.pathsep.join([str(main / ".venv" / "bin"), os.environ["PATH"]]),
    }
    names = [
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "NODE_PATH",
        "SHOP_CACHE",
        "SHOP_DOTTED",
        "SHOP_NEIGHBOUR",
    ]
    show = _show(
        f"print(*[n for n in {names!r} if n in os.environ],"
        f" str(os.environ['PATH']).startswith({str(main)!r}))"
    )
    ran = _run("launch", _settings(tmp_path, {}), tmp_path, "-", show, env=env)
    assert ran.stdout.split()[:2] == ["SHOP_NEIGHBOUR", "False"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_throwaway_secrets_go_to_a_stable_user_only_file_and_are_not_printed(tmp_path):
    repo = tmp_path / "shop"
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    only_path = json.loads(_run("throwaway", repo, env=env).stdout)
    out = Path(only_path["path"])
    assert only_path["added"] == []
    assert re.fullmatch(r"shop-[0-9a-f]{8}\.env", out.name)
    assert out.parent == tmp_path / "cfg" / "foreman" / "secrets"
    assert not out.exists()
    ran = _run("throwaway", repo, "SHOP_SECRET_KEY", "SHOP_SIGNING_KEY", env=env)
    assert json.loads(ran.stdout)["added"] == ["SHOP_SECRET_KEY", "SHOP_SIGNING_KEY"]
    again = _run("throwaway", repo, "SHOP_SECRET_KEY", "SHOP_OTHER_KEY", env=env)
    assert json.loads(again.stdout) == {"added": ["SHOP_OTHER_KEY"], "path": out.as_posix()}
    lines = out.read_text(encoding="utf-8").splitlines()
    assert [line.split("=", 1)[0] for line in lines] == [
        "SHOP_SECRET_KEY",
        "SHOP_SIGNING_KEY",
        "SHOP_OTHER_KEY",
    ]
    assert all(line.split("=", 1)[1] not in ran.stdout + again.stdout for line in lines)
    assert out.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_throwaway_secrets_wait_for_the_lock(tmp_path):
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    repo = tmp_path / "shop"
    path = Path(json.loads(_run("throwaway", repo, "SHOP_A", env=env).stdout)["path"])
    lock = path.with_suffix(".lock")
    lock.touch()
    proc = subprocess.Popen(
        [sys.executable, "-I", str(RUN), "throwaway", str(repo), "SHOP_A", "SHOP_B"],
        env=env,
        stdout=subprocess.PIPE,
        encoding="utf-8",
    )
    time.sleep(0.5)
    assert proc.poll() is None
    assert path.read_text(encoding="utf-8").count("SHOP_B") == 0
    lock.unlink()
    assert json.loads(proc.communicate(timeout=10)[0])["added"] == ["SHOP_B"]
    names = [line.split("=", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()]
    assert names == ["SHOP_A", "SHOP_B"]
    assert not lock.exists()
