from foreman.dupes import find

BODY = "\n".join(f"total += item.price * {i}" for i in range(12))


def test_duplicate_block_found_across_files(make_repo):
    root = make_repo({"a.py": BODY, "b.py": "x = 1\n" + BODY})
    blocks = find(root)["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["lines"] == 12
    assert blocks[0]["locations"] == [
        {"path": "a.py", "start": 1, "end": 12},
        {"path": "b.py", "start": 2, "end": 13},
    ]


def test_import_only_and_bracket_only_blocks_ignored(make_repo):
    imports = "\n".join(f"import mod{i}" for i in range(10))
    brackets = "\n".join("}" for _ in range(10))
    assert (
        find(make_repo({"a.py": imports, "b.py": imports, "c.js": brackets, "d.js": brackets}))[
            "blocks"
        ]
        == []
    )


def test_whitespace_differences_still_match(make_repo):
    spaced = "\n".join("    " + ln.replace(" * ", "  *  ") for ln in BODY.split("\n"))
    assert len(find(make_repo({"a.py": BODY, "b.py": spaced + "\n"}))["blocks"]) == 1


def test_block_does_not_overlap_itself(make_repo):
    assert find(make_repo({"a.py": "x = 1\n" * 12}))["blocks"] == []
