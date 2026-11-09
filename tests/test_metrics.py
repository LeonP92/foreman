from foreman.metrics import measure, percentiles


def test_percentiles_nearest_rank():
    assert percentiles([1, 2, 3, 4, 100]) == {"median": 3, "p75": 4, "p90": 100, "p95": 100}
    assert percentiles([]) == {"median": 0, "p75": 0, "p90": 0, "p95": 0}


def test_python_function_lengths(make_repo):
    src = "class A:\n    def m(self):\n        def inner():\n            return 1\n\n        return inner\n\n\ndef f():\n    return 1\n"
    root = make_repo({"a.py": src, "bad.py": "def (:\n", "README.md": "# hi\n", "b.bin": b"\0\1"})
    result = measure(root)
    assert result["files"] == [{"path": "a.py", "lines": 7}, {"path": "bad.py", "lines": 1}]
    assert result["functions"] == [
        {"path": "a.py", "name": "A.m", "start": 2, "lines": 5},
        {"path": "a.py", "name": "A.m.inner", "start": 3, "lines": 2},
        {"path": "a.py", "name": "f", "start": 9, "lines": 2},
    ]
    assert result["stats"]["function_lines"]["median"] == 2
