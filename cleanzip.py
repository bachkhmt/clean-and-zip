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

    patterns = load_excludes_file(args.excludes_file)
    patterns.extend(args.exclude)

    project_name = os.path.basename(source_dir.rstrip(os.sep)) or "project"

    print(f"[*] Dự án        : {source_dir}")
    print(f"[*] File loại trừ : {args.excludes_file}")
    print(f"[*] Số pattern    : {len(patterns)}")
    print()

    kept, size_kept, size_skipped, skipped_dirs = collect_files(
        source_dir, patterns, verbose_skip=args.verbose
    )

    print(f"[*] Giữ lại : {len(kept)} file  (~{human_size(size_kept)})")
    print(f"[*] Bỏ qua  : {len(skipped_dirs)} thư mục  (~{human_size(size_skipped)} tiết kiệm được)")
    if skipped_dirs and not args.verbose:
        preview = ", ".join(skipped_dirs[:8])
        more = f" (+{len(skipped_dirs) - 8} thư mục khác)" if len(skipped_dirs) > 8 else ""
        print(f"    -> {preview}{more}")

    if args.dry_run:
        print("\n[dry-run] Không tạo file zip.")
        return

    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.getcwd(), f"{project_name}_clean_{timestamp}.zip")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    print(f"\n[*] Đang nén -> {output_path}")
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for full_path, rel_path in kept:
            arcname = os.path.join(project_name, rel_path)
            zf.write(full_path, arcname)

    out_size = os.path.getsize(output_path)
    print(f"[+] Xong! File zip: {output_path}  ({human_size(out_size)})")


if __name__ == "__main__":
    main()
