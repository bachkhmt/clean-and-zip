#!/usr/bin/env python3
"""
cleanzip - Đóng zip 1 dự án, tự động loại bỏ các thư mục/file "nặng"
           (node_modules, .git, venv, dist, ...) mà KHÔNG đụng đến dự án gốc
           (chỉ đọc và nén, không xóa gì).

CÁCH DÙNG:
    Bạn chỉ cần CHỈ ĐỊNH đường dẫn thư mục dự án cần zip:

        python3 cleanzip.py /duong/dan/den/du-an-A

    Danh sách những gì bị loại (node_modules, __pycache__, .git, ...) nằm
    SẴN trong file "default-excludes.txt" đặt cùng thư mục với script này.
    Muốn thêm/bớt loại trừ nào -> mở file đó sửa trực tiếp, KHÔNG cần sửa code.

VÍ DỤ:
    python3 cleanzip.py ~/projects/project-A
    python3 cleanzip.py ~/projects/project-A -o ~/Desktop/project-A-clean.zip
    python3 cleanzip.py ~/projects/project-A --dry-run --verbose

    Loại bỏ thêm thư mục/file cụ thể (đường dẫn tương đối so với dự án, hoặc tuyệt đối):
    python3 cleanzip.py ~/projects/project-A -x docs/old-report.pdf data/raw assets/videos
"""

import argparse
import fnmatch
import heapq
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass, field

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    candidates = [
        os.path.join(exe_dir, "default-excludes.txt"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "default-excludes.txt"),
        os.path.join(exe_dir, "_internal", "default-excludes.txt"),
        os.path.join(os.path.dirname(exe_dir), "Resources", "default-excludes.txt"),
        os.path.join(os.path.dirname(exe_dir), "Frameworks", "default-excludes.txt"),
    ]
    PACKAGED_EXCLUDES_FILE = next((c for c in candidates if os.path.isfile(c)), candidates[0])
    EXE_EXCLUDES_FILE = os.path.join(exe_dir, "default-excludes.txt")
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PACKAGED_EXCLUDES_FILE = os.path.join(SCRIPT_DIR, "default-excludes.txt")
    EXE_EXCLUDES_FILE = PACKAGED_EXCLUDES_FILE

USER_EXCLUDES_FILE = os.path.join(os.path.expanduser("~"), ".cleanzip", "default-excludes.txt")


def get_default_excludes_file():
    """Resolve user rules first, then adjacent rules, then the packaged defaults."""
    for candidate in (USER_EXCLUDES_FILE, EXE_EXCLUDES_FILE, PACKAGED_EXCLUDES_FILE):
        if candidate and os.path.isfile(candidate):
            return candidate
    return PACKAGED_EXCLUDES_FILE


# Compatibility for callers that import this constant; operations resolve dynamically.
DEFAULT_EXCLUDES_FILE = get_default_excludes_file()


MEDIA_EXTENSIONS = {
    "*.mp3", "*.wav", "*.flac", "*.aac", "*.ogg", "*.wma", "*.m4a", "*.opus",
    "*.aiff", "*.aif", "*.mid", "*.midi", "*.ac3", "*.amr", "*.ape", "*.au",
    "*.cda", "*.dts", "*.ra", "*.voc", "*.wv",
    "*.mp4", "*.mov", "*.avi", "*.mkv", "*.wmv", "*.flv", "*.webm", "*.m4v",
    "*.mpg", "*.mpeg", "*.3gp"
}


def load_excludes_file(path: str):
    """Đọc danh sách pattern loại trừ từ file .txt (mỗi dòng 1 pattern, # là comment)."""
    if not path:
        path = get_default_excludes_file()
    if not os.path.isfile(path):
        print(f"[!] Không tìm thấy file cấu hình loại trừ: {path}", file=sys.stderr)
        print("    Sẽ chạy mà KHÔNG loại trừ gì cả trừ khi bạn dùng -e.", file=sys.stderr)
        return []

    patterns = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns


def _norm_rel(path: str) -> str:
    """Chuẩn hóa đường dẫn tương đối để so sánh: dùng '/', bỏ '/' thừa ở hai đầu,
    và không phân biệt hoa/thường trên Windows."""
    return os.path.normcase(path).replace("\\", "/").strip("/")


def resolve_exclude_paths(source_dir: str, paths):
    """
    Đổi danh sách file/thư mục người dùng chỉ định (tuyệt đối HOẶC tương đối so với
    thư mục dự án) thành tập đường dẫn tương đối đã chuẩn hóa để so khớp CHÍNH XÁC.

    Khác với pattern (fnmatch), cách này coi mọi ký tự như chữ thường, nên các tên như
    "[id].tsx" hay "file (1).txt" không bị hiểu nhầm là wildcard.

    Trả về (rel_set, invalid, missing):
      - rel_set : tập đường dẫn tương đối đã chuẩn hóa (hợp lệ, dùng để lọc)
      - invalid : các mục nằm NGOÀI dự án hoặc trỏ vào chính thư mục gốc -> bị bỏ qua
      - missing : các mục hợp lệ nhưng hiện không tồn tại trong dự án (vẫn giữ trong rel_set)
    """
    source_dir = os.path.abspath(source_dir)
    rel_set, invalid, missing = set(), [], []

    for raw in paths or []:
        p = (raw or "").strip().strip('"').strip("'")
        if not p:
            continue
        try:
            if os.path.isabs(p):
                rel = os.path.relpath(p, source_dir)
            else:
                rel = os.path.normpath(p.replace("\\", "/"))
        except ValueError:  # khác ổ đĩa trên Windows
            invalid.append(raw)
            continue

        if rel == "." or rel == ".." or rel.startswith(".." + os.sep) or os.path.isabs(rel):
            invalid.append(raw)
            continue

        rel_set.add(_norm_rel(rel))
        if not os.path.lexists(os.path.join(source_dir, rel)):
            missing.append(rel.replace("\\", "/"))

    return rel_set, invalid, missing


def is_excluded(name: str, rel_path: str, patterns) -> bool:
    """Kiểm tra tên file/thư mục có bị loại trừ không, hỗ trợ pattern whitelist bắt đầu bằng '!' (vd: !.env.example)."""
    rel_norm = rel_path.replace("\\", "/")

    # Nếu khớp quy tắc whitelist (!), luôn giữ lại
    for pat in patterns:
        if pat.startswith("!"):
            wpat = pat[1:]
            if fnmatch.fnmatch(name, wpat) or fnmatch.fnmatch(rel_norm, wpat) or wpat in rel_norm.split("/"):
                return False

    # Kiểm tra quy tắc loại trừ
    for pat in patterns:
        if not pat.startswith("!"):
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_norm, pat) or pat in rel_norm.split("/"):
                return True
    return False


def _dir_size(path: str, cancel_event=None) -> int:
    """Tính nhanh tổng dung lượng 1 thư mục (chỉ để phục vụ thống kê 'tiết kiệm được',
    KHÔNG mở nội dung file, chỉ gọi os.path.getsize nên vẫn rất nhanh kể cả với
    thư mục nhiều file như node_modules)."""
    total = 0
    for root, dirs, files in os.walk(path, topdown=True, onerror=lambda e: None):
        if cancel_event is not None and cancel_event.is_set():
            raise ZipCancelled()
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for f in files:
            if cancel_event is not None and cancel_event.is_set():
                raise ZipCancelled()
            try:
                full_path = os.path.join(root, f)
                if not os.path.islink(full_path):
                    total += os.path.getsize(full_path)
            except OSError:
                pass
    return total


def human_size(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}PB"


class ExcludeMatcher:
    """Compile exclude rules once while preserving is_excluded's matching rules."""

    def __init__(self, patterns):
        self._nc = os.path.normcase
        self.exact, self.suffix, self.other = {}, {}, []
        self.wl_exact, self.wl_other = set(), []
        self.root_only = []
        for pat in patterns:
            whitelist = pat.startswith("!")
            rule = pat[1:] if whitelist else pat
            if not whitelist and rule.startswith("/") and rule[1:] and "/" not in rule[1:]:
                self.root_only.append((self._nc(rule[1:]), pat))
                continue
            magic = any(c in rule for c in "*?[")
            if not magic and "/" not in rule:
                if whitelist:
                    self.wl_exact.add(self._nc(rule))
                else:
                    self.exact.setdefault(self._nc(rule), pat)
            elif not whitelist and rule.startswith("*.") and not any(c in rule[2:] for c in "*?[/\\"):
                self.suffix.setdefault(self._nc(rule[1:]), pat)
            elif whitelist:
                self.wl_other.append(rule)
            else:
                self.other.append((rule, pat))

    def match(self, name, rel_path):
        nc = self._nc
        rel = rel_path.replace("\\", "/")
        norm_name = nc(name)
        parts = [nc(part) for part in rel.split("/")]

        if self.wl_exact and (norm_name in self.wl_exact or any(part in self.wl_exact for part in parts)):
            return None
        for rule in self.wl_other:
            if fnmatch.fnmatch(name, rule) or fnmatch.fnmatch(rel, rule):
                return None

        if "/" not in rel:
            for rule, original in self.root_only:
                if (any(char in rule for char in "*?[") and fnmatch.fnmatch(name, rule)) or norm_name == rule:
                    return original
        matched = self.exact.get(norm_name)
        if matched:
            return matched
        for part in parts:
            matched = self.exact.get(part)
            if matched:
                return matched
        for index, char in enumerate(norm_name):
            if char == ".":
                matched = self.suffix.get(norm_name[index:])
                if matched:
                    return matched
        for rule, original in self.other:
            if fnmatch.fnmatch(name, rule) or fnmatch.fnmatch(rel, rule):
                return original
        return None

    def __call__(self, name, rel_path):
        return self.match(name, rel_path) is not None


class ZipCancelled(Exception):
    """Raised when the caller requests cancellation while writing an archive."""


STORED_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".woff", ".woff2",
    ".mp3", ".mp4", ".zip", ".gz", ".7z", ".rar",
}


def build_patterns(excludes_file=None, extra_excludes=None, include_media=False):
    """Build the effective rule list shared by ZIP creation and size analysis."""
    patterns = load_excludes_file(excludes_file or get_default_excludes_file())
    if extra_excludes:
        patterns.extend(extra_excludes)
    if include_media:
        patterns = [pattern for pattern in patterns if pattern.lower() not in MEDIA_EXTENSIONS]
    return patterns


@dataclass
class DirNode:
    name: str
    rel: str
    size: int = 0
    own_size: int = 0
    kept_size: int = 0
    file_count: int = 0
    kept_file_count: int = 0
    excluded_by: str = None
    children: list = field(default_factory=list)


def fast_dir_size(path, cancel=None):
    """Return logical bytes and regular file count without following symlinks."""
    total = count = 0
    visited = 0
    stack = [path]
    while stack:
        if cancel is not None and cancel.is_set():
            return total, count
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    visited += 1
                    if visited % 256 == 0 and cancel is not None and cancel.is_set():
                        return total, count
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                            count += 1
                    except OSError:
                        pass
        except OSError:
            pass
    return total, count


def scan_tree(source_dir, patterns, cancel=None, progress=None, top_n=30):
    """Scan a project once into an aggregate directory tree; symlinks are ignored."""
    matcher = patterns if isinstance(patterns, ExcludeMatcher) else ExcludeMatcher(patterns)
    root_path = os.path.abspath(source_dir)
    root = DirNode(os.path.basename(root_path.rstrip(os.sep)) or root_path, "")
    order, parent, top = [root], {}, []
    stack, seen = [(root, root_path)], 0

    while stack:
        if cancel is not None and cancel.is_set():
            return None, []
        node, path = stack.pop()
        try:
            entries = os.scandir(path)
        except OSError:
            continue
        try:
            with entries:
                for entry in entries:
                    seen += 1
                    if seen % 256 == 0 and cancel is not None and cancel.is_set():
                        return None, []
                    if progress and seen % 500 == 0:
                        progress(seen, node.rel)
                    try:
                        if entry.is_symlink():
                            continue
                        rel = f"{node.rel}/{entry.name}" if node.rel else entry.name
                        if entry.is_dir(follow_symlinks=False):
                            child = DirNode(entry.name, rel)
                            node.children.append(child)
                            matched = matcher.match(entry.name, rel)
                            if matched:
                                child.excluded_by = matched
                                child.size, child.file_count = fast_dir_size(entry.path, cancel=cancel)
                                if cancel is not None and cancel.is_set():
                                    return None, []
                            else:
                                parent[id(child)] = node
                                order.append(child)
                                stack.append((child, entry.path))
                        else:
                            size = entry.stat(follow_symlinks=False).st_size
                            excluded = matcher.match(entry.name, rel) is not None
                            node.own_size += size
                            node.size += size
                            node.file_count += 1
                            if not excluded:
                                node.kept_size += size
                                node.kept_file_count += 1
                            item = (size, rel, excluded)
                            if len(top) < top_n:
                                heapq.heappush(top, item)
                            elif top_n > 0 and size > top[0][0]:
                                heapq.heapreplace(top, item)
                    except OSError:
                        pass
        except OSError:
            continue

    for node in reversed(order):
        for child in node.children:
            if child.excluded_by:
                node.size += child.size
                node.file_count += child.file_count
        ancestor = parent.get(id(node))
        if ancestor is not None:
            ancestor.size += node.size
            ancestor.file_count += node.file_count
            ancestor.kept_size += node.kept_size
            ancestor.kept_file_count += node.kept_file_count
        node.children.sort(key=lambda child: child.size, reverse=True)
    return root, sorted(top, reverse=True)


def collect_files(source_dir: str, patterns, verbose_skip=False, exclude_paths=None, stats=None, cancel_event=None):
    """
    Duyệt cây thư mục, trả về (kept, size_kept, size_skipped, skipped_dirs, skipped_files_count).

    exclude_paths: tập đường dẫn tương đối (đã chuẩn hóa bằng resolve_exclude_paths) mà
    người dùng chỉ định loại bỏ. Mục này được ưu tiên hơn cả whitelist "!" vì đó là
    lựa chọn chủ động của người dùng.
    """
    exclude_paths = exclude_paths or set()
    if not isinstance(patterns, ExcludeMatcher):
        patterns = ExcludeMatcher(patterns)
    kept = []
    skipped_dirs = []
    skipped_files_count = 0
    size_kept = 0
    size_skipped = 0
    skipped_symlinks = 0

    source_dir = os.path.abspath(source_dir)

    for root, dirs, files in os.walk(source_dir, topdown=True):
        if cancel_event is not None and cancel_event.is_set():
            raise ZipCancelled()
        rel_root = os.path.relpath(root, source_dir)
        if rel_root == ".":
            rel_root = ""

        # Lọc thư mục con ngay tại chỗ để os.walk KHÔNG đi vào bên trong
        # (quan trọng: tránh phải quét cả node_modules khổng lồ)
        new_dirs = []
        for d in dirs:
            if cancel_event is not None and cancel_event.is_set():
                raise ZipCancelled()
            full_dir = os.path.join(root, d)
            if os.path.islink(full_dir):
                skipped_symlinks += 1
                continue
            rel_path = os.path.join(rel_root, d) if rel_root else d
            if (exclude_paths and _norm_rel(rel_path) in exclude_paths) or patterns(d, rel_path):
                skipped_dirs.append(rel_path)
                size_skipped += _dir_size(full_dir, cancel_event=cancel_event)
                if verbose_skip:
                    print(f"  [-] bỏ qua thư mục: {rel_path}/")
            else:
                new_dirs.append(d)
        dirs[:] = new_dirs

        for fname in files:
            if cancel_event is not None and cancel_event.is_set():
                raise ZipCancelled()
            rel_path = os.path.join(rel_root, fname) if rel_root else fname
            full_path = os.path.join(root, fname)
            if os.path.islink(full_path):
                skipped_symlinks += 1
                continue
            if (exclude_paths and _norm_rel(rel_path) in exclude_paths) or patterns(fname, rel_path):
                skipped_files_count += 1
                if verbose_skip:
                    print(f"  [-] bỏ qua file: {rel_path}")
                try:
                    size_skipped += os.path.getsize(full_path)
                except OSError:
                    pass
                continue
            try:
                fsize = os.path.getsize(full_path)
            except OSError:
                fsize = 0
            size_kept += fsize
            kept.append((full_path, rel_path))

    if stats is not None:
        stats["symlinks"] = skipped_symlinks
    return kept, size_kept, size_skipped, skipped_dirs, skipped_files_count


def get_downloads_folder() -> str:
    """Trả về đường dẫn thư mục Downloads của hệ điều hành."""
    if sys.platform == "win32":
        try:
            import winreg
            sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
                val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
                if os.path.isdir(val):
                    return val
        except Exception:
            pass
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(downloads, exist_ok=True)
    return downloads


def zip_project(
    source_dir: str,
    output_path: str = None,
    excludes_file: str = None,
    extra_excludes: list = None,
    exclude_paths: list = None,
    include_media: bool = False,
    progress_callback=None,
    dry_run: bool = False,
    verbose: bool = False,
    cancel_event=None,
):
    """
    Nén dự án sau khi lọc các file/thư mục loại trừ.
    Hỗ trợ progress_callback(stage, current, total, message) phục vụ GUI.

    exclude_paths: danh sách file/thư mục cụ thể cần loại bỏ thêm (tuyệt đối hoặc tương đối
    so với source_dir). Khớp chính xác theo đường dẫn, không dùng wildcard.
    """
    source_dir = os.path.abspath(source_dir)
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Không tìm thấy thư mục: {source_dir}")

    patterns = ExcludeMatcher(build_patterns(excludes_file or get_default_excludes_file(), extra_excludes, include_media))

    project_name = os.path.basename(source_dir.rstrip(os.sep)) or "project"

    if progress_callback:
        progress_callback("scan", 0, 0, f"Đang quét thư mục dự án: {project_name}...")

    exclude_set, invalid_excludes, missing_excludes = resolve_exclude_paths(source_dir, exclude_paths)

    scan_stats = {}
    kept, size_kept, size_skipped, skipped_dirs, skipped_files_count = collect_files(
        source_dir, patterns, verbose_skip=verbose, exclude_paths=exclude_set, stats=scan_stats,
        cancel_event=cancel_event,
    )

    total_files = len(kept)

    if not output_path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.getcwd(), f"{project_name}_clean_{timestamp}.zip")
    else:
        output_path = os.path.abspath(output_path)

    out_size = 0
    failed = []
    if not dry_run:
        if cancel_event is not None and cancel_event.is_set():
            raise ZipCancelled()
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        if progress_callback:
            progress_callback("compress", 0, total_files, f"Bắt đầu nén {total_files} files...")

        tmp_path = output_path + ".part"
        try:
            with zipfile.ZipFile(
                tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6, strict_timestamps=False
            ) as zf:
                for idx, (full_path, rel_path) in enumerate(kept, start=1):
                    if cancel_event is not None and cancel_event.is_set():
                        raise ZipCancelled()
                    arcname = os.path.join(project_name, rel_path)
                    try:
                        compression = (
                            zipfile.ZIP_STORED
                            if os.path.splitext(rel_path)[1].lower() in STORED_EXT
                            else zipfile.ZIP_DEFLATED
                        )
                        zf.write(full_path, arcname, compress_type=compression)
                    except (OSError, ValueError) as e:
                        failed.append(rel_path)
                        if verbose:
                            print(f"  [!] bỏ qua (lỗi khi đọc): {rel_path} — {e}")
                    if cancel_event is not None and cancel_event.is_set():
                        raise ZipCancelled()
                    if progress_callback and (idx % 10 == 0 or idx == total_files):
                        progress_callback("compress", idx, total_files, f"Đang nén ({idx}/{total_files}): {rel_path}")
            if cancel_event is not None and cancel_event.is_set():
                raise ZipCancelled()
            os.replace(tmp_path, output_path)
        except BaseException:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

        out_size = os.path.getsize(output_path)
        if failed:
            print(f"[!] {len(failed)} file bị bỏ qua do lỗi đọc (xem --verbose để biết chi tiết)", file=sys.stderr)

    result = {
        "project_name": project_name,
        "source_dir": source_dir,
        "output_path": output_path,
        "kept_count": total_files,
        "kept_size": size_kept,
        "skipped_size": size_skipped,
        "skipped_dirs_count": len(skipped_dirs),
        "skipped_dirs": skipped_dirs,
        "skipped_files_count": skipped_files_count,
        "skipped_symlinks": scan_stats.get("symlinks", 0),
        "invalid_exclude_paths": invalid_excludes,
        "missing_exclude_paths": missing_excludes,
        "compressed_size": out_size,
        "failed_count": len(failed) if not dry_run else 0,
    }

    if progress_callback:
        progress_callback("done", total_files, total_files, "Hoàn tất nén dự án!")

    return result


def parse_size(text: str) -> int:
    """Parse a byte count such as 10MB, 500k, or 1.5G."""
    match = re.fullmatch(r"\s*([\d.]+)\s*([KMGT]?)B?\s*", str(text), re.I)
    if not match:
        raise argparse.ArgumentTypeError(
            f"Dung lượng không hợp lệ: {text!r} (ví dụ: 500KB, 10MB, 1.5GB)"
        )
    multiplier = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
    try:
        return int(float(match.group(1)) * multiplier[match.group(2).upper()])
    except (ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError(f"Dung lượng không hợp lệ: {text!r}") from exc


def print_size_report(root, top_files, depth=2, min_size=1024 ** 2):
    """Print a compact directory-size tree and suggestions for -x."""
    print(
        f"[*] Tổng {human_size(root.size)}  |  sẽ nén (luật mặc định) "
        f"{human_size(root.kept_size)}  |  {root.file_count} file\n"
    )

    def walk(node, level):
        for child in node.children:
            if child.size < min_size:
                continue
            ratio = child.size / root.size if root.size else 0
            note = f"  [loại mặc định: {child.excluded_by}]" if child.excluded_by else ""
            label = ("  " * level + child.name + "/")[:44]
            print(f"{label:<44}{human_size(child.size):>10}  {'█' * round(ratio * 10):<10}{note}")
            if level + 1 < depth and not child.excluded_by:
                walk(child, level + 1)

    walk(root, 0)
    heavy, stack = [], [root]
    while stack:
        node = stack.pop()
        if node.excluded_by:
            continue
        if node.rel and node.own_size >= 10 * 1024 ** 2:
            heavy.append(node)
        stack.extend(node.children)
    heavy.sort(key=lambda node: node.own_size, reverse=True)
    if top_files:
        print("\nFile nặng nhất:")
        for size, rel, excluded in top_files[:10]:
            suffix = "  (đã bị loại bởi luật)" if excluded else ""
            print(f"  {human_size(size):>10}  {rel}{suffix}")
    if heavy:
        print("\nGợi ý loại bỏ thêm (thư mục chứa nhiều dữ liệu trực tiếp):")
        print("  " + " ".join(f"-x {node.rel}" for node in heavy[:5]))


def main():
    parser = argparse.ArgumentParser(
        description="Đóng zip 1 dự án, tự động loại bỏ node_modules, .git, venv... theo file default-excludes.txt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", help="Đường dẫn thư mục dự án cần đóng zip (BẮT BUỘC - đây là phần bạn chỉ định)")
    parser.add_argument("-o", "--output", help="Đường dẫn file zip đầu ra (mặc định: <tên_dự_án>_clean_<timestamp>.zip)")
    parser.add_argument("-e", "--exclude", nargs="*", default=[], help="Thêm pattern loại trừ tạm thời, chỉ áp dụng cho lần chạy này")
    parser.add_argument(
        "-x", "--exclude-path", action="append", default=[], metavar="PATH",
        help="Loại bỏ thêm 1 file/thư mục cụ thể (đường dẫn tương đối so với dự án hoặc tuyệt đối). "
             "Có thể lặp lại nhiều lần: -x docs/old.pdf -x data/raw",
    )
    parser.add_argument("--excludes-file", default=None, help="Dùng file danh sách loại trừ khác thay vì default-excludes.txt")
    parser.add_argument("--include-media", action="store_true", help="Giữ lại file audio/video thay vì loại bỏ")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê, không tạo file zip")
    parser.add_argument("--verbose", action="store_true", help="In chi tiết các file/thư mục bị bỏ qua")
    parser.add_argument("--sizes", action="store_true", help="Chỉ phân tích dung lượng từng thư mục (không nén)")
    parser.add_argument("--depth", type=int, default=2, help="Độ sâu in ra khi dùng --sizes (mặc định 2)")
    parser.add_argument("--min-size", type=parse_size, default="1MB", help="Ẩn thư mục nhỏ hơn mức này khi dùng --sizes")

    args = parser.parse_args()

    source_dir = os.path.abspath(args.source)
    if not os.path.isdir(source_dir):
        print(f"[x] Không tìm thấy thư mục: {source_dir}", file=sys.stderr)
        sys.exit(1)

    if args.sizes:
        if args.depth < 1:
            parser.error("--depth phải lớn hơn hoặc bằng 1")
        root, top_files = scan_tree(
            source_dir,
            ExcludeMatcher(build_patterns(args.excludes_file or get_default_excludes_file(), args.exclude, args.include_media)),
        )
        if root is None:
            return
        print(f"[*] Dự án        : {source_dir}")
        print_size_report(root, top_files, depth=args.depth, min_size=args.min_size)
        return

    project_name = os.path.basename(source_dir.rstrip(os.sep)) or "project"
    print(f"[*] Dự án        : {source_dir}")
    print(f"[*] File loại trừ : {args.excludes_file or get_default_excludes_file()}")

    if args.output:
        out_path = os.path.abspath(args.output)
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(os.getcwd(), f"{project_name}_clean_{timestamp}.zip")

    res = zip_project(
        source_dir=source_dir,
        output_path=out_path,
        excludes_file=args.excludes_file or get_default_excludes_file(),
        extra_excludes=args.exclude,
        exclude_paths=args.exclude_path,
        include_media=args.include_media,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    print(f"[*] Giữ lại : {res['kept_count']} file  (~{human_size(res['kept_size'])})")
    print(f"[*] Bỏ qua  : {res['skipped_dirs_count']} thư mục, {res['skipped_files_count']} file  (~{human_size(res['skipped_size'])} tiết kiệm được)")
    if res["skipped_symlinks"]:
        print(f"[*] Bỏ qua  : {res['skipped_symlinks']} liên kết tượng trưng (symlink)")
    for item in res["invalid_exclude_paths"]:
        print(f"[!] Bỏ qua mục -x nằm ngoài dự án (hoặc là thư mục gốc): {item}", file=sys.stderr)
    for item in res["missing_exclude_paths"]:
        print(f"[!] Mục -x không tồn tại trong dự án: {item}", file=sys.stderr)
    if res['skipped_dirs'] and not args.verbose:
        preview = ", ".join(res['skipped_dirs'][:8])
        more = f" (+{len(res['skipped_dirs']) - 8} thư mục khác)" if len(res['skipped_dirs']) > 8 else ""
        print(f"    -> {preview}{more}")

    if args.dry_run:
        print("\n[dry-run] Không tạo file zip.")
        return

    print(f"\n[+] Xong! File zip: {res['output_path']}  ({human_size(res['compressed_size'])})")


if __name__ == "__main__":
    main()
