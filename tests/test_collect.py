import os
import threading
import zipfile

import pytest

import cleanzip


def test_collect_skips_and_counts_file_and_directory_symlinks(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("Symlinks are unavailable")
    source = tmp_path / "project"
    source.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    (source / "inside.txt").write_text("inside", encoding="utf-8")
    try:
        (source / "link.txt").symlink_to(target)
        (source / "linked-dir").symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks requires additional privileges")

    stats = {}
    kept, kept_size, _skipped_size, _dirs, _files = cleanzip.collect_files(
        str(source), [], stats=stats
    )
    assert [rel for _path, rel in kept] == ["inside.txt"]
    assert kept_size == len("inside")
    assert stats["symlinks"] == 2


def test_old_mtime_is_clamped_in_archive(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    old_file = source / "old.txt"
    old_file.write_text("old", encoding="utf-8")
    timestamp = 157766400  # 1975-01-01 UTC
    os.utime(old_file, (timestamp, timestamp))
    output = tmp_path / "result.zip"

    result = cleanzip.zip_project(str(source), str(output), excludes_file="missing.txt")

    assert result["failed_count"] == 0
    with zipfile.ZipFile(output) as archive:
        assert archive.getinfo("project/old.txt").date_time == (1980, 1, 1, 0, 0, 0)


def test_cancel_removes_partial_archive(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    for index in range(4):
        (source / f"{index}.txt").write_bytes(b"x" * 1024)
    output = tmp_path / "cancelled.zip"
    cancel = threading.Event()
    observed_partial = []

    def request_cancel(stage, current, total, _message):
        if stage == "compress" and current == total and total:
            observed_partial.append((tmp_path / "cancelled.zip.part").exists())
            cancel.set()

    with pytest.raises(cleanzip.ZipCancelled):
        cleanzip.zip_project(
            str(source), str(output), excludes_file="missing.txt",
            progress_callback=request_cancel, cancel_event=cancel,
        )

    assert not output.exists()
    assert not (tmp_path / "cancelled.zip.part").exists()
    assert observed_partial == [True]


def test_cancel_event_stops_during_project_scan(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "file.txt").write_text("x", encoding="utf-8")
    output = tmp_path / "cancelled.zip"
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(cleanzip.ZipCancelled):
        cleanzip.zip_project(str(source), str(output), excludes_file="missing.txt", cancel_event=cancel)

    assert not output.exists()
    assert not (tmp_path / "cancelled.zip.part").exists()


def test_exclude_path_with_brackets_is_literal(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "[id].tsx").write_text("selected", encoding="utf-8")
    (source / "i.tsx").write_text("keep", encoding="utf-8")
    paths, invalid, missing = cleanzip.resolve_exclude_paths(str(source), ["[id].tsx"])

    kept, *_rest = cleanzip.collect_files(str(source), [], exclude_paths=paths)

    assert not invalid
    assert not missing
    assert [rel for _path, rel in kept] == ["i.tsx"]


def test_zip_project_reports_skipped_symlinks(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("Symlinks are unavailable")
    source = tmp_path / "project"
    source.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("secret", encoding="utf-8")
    try:
        (source / "shortcut.txt").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks requires additional privileges")
    output = tmp_path / "result.zip"

    result = cleanzip.zip_project(str(source), str(output), excludes_file="missing.txt")

    assert result["skipped_symlinks"] == 1
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == []


def test_already_compressed_file_types_are_stored(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "image.png").write_bytes(b"image")
    (source / "source.py").write_text("print('hello')", encoding="utf-8")
    output = tmp_path / "result.zip"

    cleanzip.zip_project(str(source), str(output), excludes_file="missing.txt")

    with zipfile.ZipFile(output) as archive:
        assert archive.getinfo("project/image.png").compress_type == zipfile.ZIP_STORED
        assert archive.getinfo("project/source.py").compress_type == zipfile.ZIP_DEFLATED
