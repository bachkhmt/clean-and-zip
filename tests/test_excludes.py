import argparse
import ntpath
import os

import pytest

import cleanzip


@pytest.mark.parametrize(
    "patterns,name,rel_path",
    [
        (["node_modules", "*.pyc", "*.log"], "node_modules", "packages/app/node_modules"),
        (["*.pyc"], "cache.PYC", "cache.PYC"),
        (["[Bb]in", "[Dd]ebug"], "Bin", "Bin"),
        (["*.tar.gz", "foo*bar"], "archive.tar.gz", "nested/archive.tar.gz"),
        ([".env", "!.env.example"], ".env.example", ".env.example"),
        (["secrets.*", "!secrets.example"], "secrets.example", "config/secrets.example"),
        (["*.tmp", "!keep.tmp"], "keep.tmp", "keep.tmp"),
        (["id_rsa*"], "id_rsa.pub", "keys/id_rsa.pub"),
    ],
)
def test_compiled_matcher_matches_legacy_rules(patterns, name, rel_path):
    assert cleanzip.ExcludeMatcher(patterns)(name, rel_path) == cleanzip.is_excluded(name, rel_path, patterns)


def test_matcher_is_case_insensitive_with_windows_normcase(monkeypatch):
    monkeypatch.setattr(cleanzip.os.path, "normcase", ntpath.normcase)
    matcher = cleanzip.ExcludeMatcher(["node_modules", "*.PYC", "!.ENV.EXAMPLE"])
    assert matcher("Node_Modules", "Packages/Node_Modules")
    assert matcher("cache.pyc", "cache.pyc")
    assert not matcher(".env.example", ".env.example")


def test_root_only_rules_preserve_same_named_nested_source():
    matcher = cleanzip.ExcludeMatcher(["/bin", "/[Bb]in", "/dist", "node_modules"])
    assert matcher("bin", "bin")
    assert matcher("Bin", "Bin")
    assert matcher("dist", "dist")
    assert not matcher("bin", "scripts/bin")
    assert not matcher("dist", "packages/web/dist")
    assert matcher("node_modules", "packages/web/src/node_modules")


def test_parse_size():
    assert cleanzip.parse_size("5MB") == 5 * 1024**2
    assert cleanzip.parse_size("1.5G") == int(1.5 * 1024**3)
    with pytest.raises(argparse.ArgumentTypeError):
        cleanzip.parse_size("lots")


def test_default_rule_file_precedence(tmp_path, monkeypatch):
    user = tmp_path / "user.txt"
    adjacent = tmp_path / "adjacent.txt"
    packaged = tmp_path / "packaged.txt"
    for path in (user, adjacent, packaged):
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(cleanzip, "USER_EXCLUDES_FILE", str(user))
    monkeypatch.setattr(cleanzip, "EXE_EXCLUDES_FILE", str(adjacent))
    monkeypatch.setattr(cleanzip, "PACKAGED_EXCLUDES_FILE", str(packaged))

    assert cleanzip.get_default_excludes_file() == str(user)
    user.unlink()
    assert cleanzip.get_default_excludes_file() == str(adjacent)
    adjacent.unlink()
    assert cleanzip.get_default_excludes_file() == str(packaged)


def test_include_media_removes_default_audio_video_rules(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "clip.mp4").write_bytes(b"video")
    (source / "voice.mp3").write_bytes(b"audio")
    default_rules = cleanzip.build_patterns(cleanzip.PACKAGED_EXCLUDES_FILE)
    include_rules = cleanzip.build_patterns(cleanzip.PACKAGED_EXCLUDES_FILE, include_media=True)

    default_kept, *_ = cleanzip.collect_files(str(source), default_rules)
    include_kept, *_ = cleanzip.collect_files(str(source), include_rules)

    assert default_kept == []
    assert {os.path.basename(path) for path, _rel in include_kept} == {"clip.mp4", "voice.mp3"}
