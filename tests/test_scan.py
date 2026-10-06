import os
import sys
import threading

import cleanzip


def _assert_tree(node):
    if node.excluded_by:
        return
    assert node.size == node.own_size + sum(child.size for child in node.children), node.rel
    assert node.kept_size <= node.size
    for child in node.children:
        _assert_tree(child)


def test_scan_sizes_and_kept_totals_match_file_collection(tmp_path):
    source = tmp_path / "project"
    (source / "data" / "raw").mkdir(parents=True)
    (source / "node_modules" / "pkg").mkdir(parents=True)
    (source / "data" / "root.bin").write_bytes(b"a" * 13)
    (source / "data" / "raw" / "model.pt").write_bytes(b"b" * 29)
    (source / "node_modules" / "pkg" / "index.js").write_bytes(b"c" * 31)
    (source / "root.txt").write_bytes(b"d" * 7)
    patterns = ["node_modules", "*.pt"]

    root, _top = cleanzip.scan_tree(str(source), patterns)
    kept, kept_size, _skipped, _dirs, _files = cleanzip.collect_files(str(source), patterns)

    _assert_tree(root)
    assert root.size == 80
    assert root.kept_size == kept_size == 20
    assert root.file_count == 4
    assert root.kept_file_count == len(kept) == 2
    node_modules = next(child for child in root.children if child.name == "node_modules")
    assert node_modules.excluded_by == "node_modules"
    assert node_modules.children == []


def test_scan_does_not_create_descendants_for_excluded_directory(tmp_path):
    source = tmp_path / "project"
    hidden = source / "node_modules" / "nested" / "deeper"
    hidden.mkdir(parents=True)
    (hidden / "package.js").write_text("x", encoding="utf-8")

    root, _top = cleanzip.scan_tree(str(source), ["node_modules"])

    node_modules = root.children[0]
    assert node_modules.name == "node_modules"
    assert node_modules.size == 1
    assert node_modules.children == []


def test_scan_cancel_returns_empty_result(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "file.txt").write_text("x", encoding="utf-8")
    cancel = threading.Event()
    cancel.set()

    assert cleanzip.scan_tree(str(source), [], cancel=cancel) == (None, [])


def test_scan_ignores_symlinks(tmp_path):
    if not hasattr(os, "symlink"):
        return
    source = tmp_path / "project"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (source / "link.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        return

    root, _top = cleanzip.scan_tree(str(source), [])
    assert root.size == 0
    assert root.file_count == 0


def test_unreadable_directory_is_skipped_without_crashing(tmp_path, monkeypatch):
    source = tmp_path / "project"
    blocked = source / "blocked"
    blocked.mkdir(parents=True)
    real_scandir = os.scandir

    def guarded_scandir(path):
        if os.fspath(path) == os.fspath(blocked):
            raise PermissionError("unreadable")
        return real_scandir(path)

    monkeypatch.setattr(cleanzip.os, "scandir", guarded_scandir)
    root, _top = cleanzip.scan_tree(str(source), [])

    assert root.size == 0
    assert root.children[0].name == "blocked"


def test_default_rules_keep_nested_bin_but_drop_root_bin_and_deep_node_modules(tmp_path):
    source = tmp_path / "project"
    (source / "bin").mkdir(parents=True)
    (source / "scripts" / "bin").mkdir(parents=True)
    (source / "packages" / "app" / "node_modules").mkdir(parents=True)
    (source / "bin" / "generated.dat").write_text("drop", encoding="utf-8")
    (source / "scripts" / "bin" / "run.sh").write_text("keep", encoding="utf-8")
    (source / "packages" / "app" / "node_modules" / "pkg.js").write_text("drop", encoding="utf-8")

    kept, *_rest = cleanzip.collect_files(
        str(source), cleanzip.build_patterns(cleanzip.PACKAGED_EXCLUDES_FILE)
    )

    assert {rel.replace("\\", "/") for _path, rel in kept} == {"scripts/bin/run.sh"}


def test_sizes_cli_prints_report_and_does_not_create_zip(tmp_path, monkeypatch, capsys):
    source = tmp_path / "project"
    source.mkdir()
    large_file = source / "large.dat"
    with large_file.open("wb") as file:
        file.truncate(6 * 1024**2)
    monkeypatch.setattr(
        sys, "argv", ["cleanzip.py", str(source), "--sizes", "--depth", "3", "--min-size", "5MB"]
    )

    cleanzip.main()

    output = capsys.readouterr().out
    assert "Tổng 6.0MB" in output
    assert "large.dat" in output
    assert not list(tmp_path.glob("*.zip"))
