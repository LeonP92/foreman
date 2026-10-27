import functools
import http.server
import os
import subprocess
import threading

import pytest

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.com",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.com",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


@pytest.fixture
def make_repo(tmp_path):
    env = {
        **os.environ,
        **GIT_ENV,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }

    def git(*args):
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
        )

    def write(files):
        for name, content in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8", newline="")

    def make(files, commits=None):
        git("init", "-q")
        write(files)
        git("add", "-A")
        git("commit", "-q", "--allow-empty", "-m", "initial")
        for i, extra in enumerate(commits or []):
            write(extra)
            git("add", "-A")
            git("commit", "-q", "--allow-empty", "-m", f"commit {i + 1}")
        return tmp_path

    return make


@pytest.fixture
def serve():
    """Serves a directory over HTTP on a free port; returns its base URL."""
    servers = []

    def start(directory):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()
