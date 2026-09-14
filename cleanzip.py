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
"""

import argparse
import fnmatch
import os
import sys
import time
import zipfile

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    if os.path.isfile(os.path.join(exe_dir, "default-excludes.txt")):
        DEFAULT_EXCLUDES_FILE = os.path.join(exe_dir, "default-excludes.txt")
    else:
        DEFAULT_EXCLUDES_FILE = os.path.join(getattr(sys, "_MEIPASS", exe_dir), "default-excludes.txt")
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    DEFAULT_EXCLUDES_FILE = os.path.join(SCRIPT_DIR, "default-excludes.txt")


def load_excludes_file(path: str):
    """Đọc danh sách pattern loại trừ từ file .txt (mỗi dòng 1 pattern, # là comment)."""
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


def human_size(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}PB"


def collect_files(source_dir: str, patterns, verbose_skip=False):
    """Duyệt cây thư mục, trả về danh sách file giữ lại + thống kê."""
    kept = []
    skipped_dirs = []
    size_kept = 0
    size_skipped = 0

    source_dir = os.path.abspath(source_dir)

    for root, dirs, files in os.walk(source_dir, topdown=True):
        rel_root = os.path.relpath(root, source_dir)
        if rel_root == ".":
            rel_root = ""

        # Lọc thư mục con ngay tại chỗ để os.walk KHÔNG đi vào bên trong
        # (quan trọng: tránh phải quét cả node_modules khổng lồ)
        new_dirs = []
        for d in dirs:
            rel_path = os.path.join(rel_root, d) if rel_root else d
            if is_excluded(d, rel_path, patterns):
                skipped_dirs.append(rel_path)
                if verbose_skip:
                    print(f"  [-] bỏ qua thư mục: {rel_path}/")
            else:
                new_dirs.append(d)
        dirs[:] = new_dirs

        for fname in files:
            rel_path = os.path.join(rel_root, fname) if rel_root else fname
            full_path = os.path.join(root, fname)
            if is_excluded(fname, rel_path, patterns):
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

    return kept, size_kept, size_skipped, skipped_dirs


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
    excludes_file: str = DEFAULT_EXCLUDES_FILE,
    extra_excludes: list = None,
    progress_callback=None,
    dry_run: bool = False,
    verbose: bool = False,
):
    """
    Nén dự án sau khi lọc các file/thư mục loại trừ.
    Hỗ trợ progress_callback(stage, current, total, message) phục vụ GUI.
    """
    source_dir = os.path.abspath(source_dir)
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Không tìm thấy thư mục: {source_dir}")

    patterns = load_excludes_file(excludes_file)
    if extra_excludes:
        patterns.extend(extra_excludes)

    project_name = os.path.basename(source_dir.rstrip(os.sep)) or "project"

    if progress_callback:
        progress_callback("scan", 0, 0, f"Đang quét thư mục dự án: {project_name}...")

    kept, size_kept, size_skipped, skipped_dirs = collect_files(
        source_dir, patterns, verbose_skip=verbose
    )

    total_files = len(kept)

    if not output_path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.getcwd(), f"{project_name}_clean_{timestamp}.zip")
    else:
        output_path = os.path.abspath(output_path)

    out_size = 0
    if not dry_run:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        if progress_callback:
            progress_callback("compress", 0, total_files, f"Bắt đầu nén {total_files} files...")

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for idx, (full_path, rel_path) in enumerate(kept, start=1):
                arcname = os.path.join(project_name, rel_path)
                zf.write(full_path, arcname)
                if progress_callback and (idx % 10 == 0 or idx == total_files):
                    progress_callback("compress", idx, total_files, f"Đang nén ({idx}/{total_files}): {rel_path}")

        out_size = os.path.getsize(output_path)

    result = {
        "project_name": project_name,
        "source_dir": source_dir,
        "output_path": output_path,
        "kept_count": total_files,
        "kept_size": size_kept,
        "skipped_size": size_skipped,
        "skipped_dirs_count": len(skipped_dirs),
        "skipped_dirs": skipped_dirs,
        "compressed_size": out_size,
    }

    if progress_callback:
        progress_callback("done", total_files, total_files, "Hoàn tất nén dự án!")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Đóng zip 1 dự án, tự động loại bỏ node_modules, .git, venv... theo file default-excludes.txt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", help="Đường dẫn thư mục dự án cần đóng zip (BẮT BUỘC - đây là phần bạn chỉ định)")
    parser.add_argument("-o", "--output", help="Đường dẫn file zip đầu ra (mặc định: <tên_dự_án>_clean_<timestamp>.zip)")
    parser.add_argument("-e", "--exclude", nargs="*", default=[], help="Thêm pattern loại trừ tạm thời, chỉ áp dụng cho lần chạy này")
    parser.add_argument("--excludes-file", default=DEFAULT_EXCLUDES_FILE, help="Dùng file danh sách loại trừ khác thay vì default-excludes.txt")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê, không tạo file zip")
    parser.add_argument("--verbose", action="store_true", help="In chi tiết các file/thư mục bị bỏ qua")

    args = parser.parse_args()

    source_dir = os.path.abspath(args.source)
    if not os.path.isdir(source_dir):
        print(f"[x] Không tìm thấy thư mục: {source_dir}", file=sys.stderr)
        sys.exit(1)

    project_name = os.path.basename(source_dir.rstrip(os.sep)) or "project"
    print(f"[*] Dự án        : {source_dir}")
    print(f"[*] File loại trừ : {args.excludes_file}")

    if args.output:
        out_path = os.path.abspath(args.output)
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(os.getcwd(), f"{project_name}_clean_{timestamp}.zip")

    res = zip_project(
        source_dir=source_dir,
        output_path=out_path,
        excludes_file=args.excludes_file,
        extra_excludes=args.exclude,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    print(f"[*] Giữ lại : {res['kept_count']} file  (~{human_size(res['kept_size'])})")
    print(f"[*] Bỏ qua  : {res['skipped_dirs_count']} thư mục  (~{human_size(res['skipped_size'])} tiết kiệm được)")
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
