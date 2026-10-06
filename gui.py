#!/usr/bin/env python3
"""
CleanZip Desktop UI
Giao diện trực quan, hiện đại cho tool CleanZip.
Hỗ trợ dán nhanh, duyệt thư mục, lịch sử gần đây, chuyển đổi theme sáng/tối,
tùy chọn bỏ qua media, mở trực tiếp file zip và thư mục Downloads,
và chọn thêm thư mục / file cụ thể để loại bỏ (được nhớ theo từng dự án).
"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from cleanzip import (
    ExcludeMatcher,
    PACKAGED_EXCLUDES_FILE,
    USER_EXCLUDES_FILE,
    build_patterns,
    get_default_excludes_file,
    get_downloads_folder,
    human_size,
    resolve_exclude_paths,
    scan_tree,
    ZipCancelled,
    zip_project,
)
from config import load_config, save_config
from size_explorer import SizeExplorer
from version import __version__


def get_resource_path(relative_path: str) -> str:
    """Lấy đường dẫn tài nguyên tuyệt đối, tương thích cả khi chạy source code và khi đóng gói PyInstaller."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            getattr(sys, "_MEIPASS", ""),
            os.path.join(exe_dir, "_internal"),
            exe_dir,
            os.path.join(os.path.dirname(exe_dir), "Resources"),
            os.path.join(os.path.dirname(exe_dir), "Frameworks"),
        ]
        for c in candidates:
            if c:
                target = os.path.join(c, relative_path)
                if os.path.exists(target):
                    return target
        base_path = getattr(sys, "_MEIPASS", exe_dir)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def _nk(rel_path: str) -> str:
    """Khóa so sánh đường dẫn tương đối: dùng '/', không phân biệt hoa/thường trên Windows."""
    return os.path.normcase(rel_path).replace("\\", "/").strip("/")


def _shorten(text: str, max_len: int = 72) -> str:
    """Rút gọn chuỗi dài ở giữa để vừa 1 dòng."""
    if len(text) <= max_len:
        return text
    keep = max_len - 3
    head = keep // 3
    return text[:head] + "..." + text[-(keep - head):]


class CleanZipApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.cfg = load_config()
        theme_mode = self.cfg.get("theme", "Dark")
        ctk.set_appearance_mode(theme_mode)
        ctk.set_default_color_theme("blue")

        self.title(f"CleanZip Desktop v{__version__} - Nén Dự Án Gọn Sạch")
        screen_h = self.winfo_screenheight()
        self.geometry(f"760x{min(860, max(600, screen_h - 100))}")
        self.minsize(720, 560)

        # Cấu hình icon cửa sổ và thanh tác vụ Windows
        if sys.platform == "win32":
            try:
                from ctypes import windll
                # 1. Định danh AppUserModelID để Windows Taskbar hiển thị icon riêng của app
                windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"bachkhmt.cleanzip.desktop.v{__version__}")
            except Exception:
                pass

        ico_path = get_resource_path(os.path.join("public", "cleanzip.ico"))
        if os.path.exists(ico_path):
            try:
                if sys.platform == "win32":
                    self.iconbitmap(default=ico_path)
                    self.wm_iconbitmap(ico_path)
                else:
                    from PIL import ImageTk
                    png_path = get_resource_path(os.path.join("public", "cleanzip_square.png"))
                    if os.path.exists(png_path):
                        photo = ImageTk.PhotoImage(file=png_path)
                        self.iconphoto(True, photo)
            except Exception:
                pass

        self.downloads_dir = get_downloads_folder()
        self.is_zipping = False
        self.last_zip_path = None
        self.recent_list = [p for p in self.cfg.get("history", []) if os.path.isdir(p)]

        # Danh sách file/thư mục người dùng chọn loại bỏ thêm (thuộc về dự án self.excl_key)
        self.excl_items = []   # [{"path": "data/raw", "kind": "dir"}, ...] - path tương đối so với dự án
        self.excl_key = None
        self._sync_job = None
        self.size_explorer = None
        self.scan_cache = None
        self._scan_q = queue.Queue()
        self._scan_gen = 0
        self._scan_cancel = threading.Event()
        self._scan_job = None
        self._scan_poll_job = None
        self._recent_map = {}
        self._zip_q = queue.Queue()
        self._cancel_event = threading.Event()

        self._build_ui()
        if sys.platform == "darwin":
            try:
                self.lift()
                self.focus_force()
            except Exception:
                pass

    def _build_ui(self):
        # Cuộn được để không bị cắt trên màn hình nhỏ khi có thêm thẻ "Loại bỏ thêm"
        self.main_container = ctk.CTkScrollableFrame(self, corner_radius=16, fg_color=("gray95", "gray12"))
        self.main_container.pack(fill="both", expand=True, padx=18, pady=18)

        # ---------------- HEADER ----------------
        self.header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(15, 8))

        self.header_left = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.header_left.pack(side="left", fill="y")

        self.title_box = ctk.CTkFrame(self.header_left, fg_color="transparent")
        self.title_box.pack(anchor="w")

        # Hiển thị Logo CleanZip 3D trong Header
        logo_png = get_resource_path(os.path.join("public", "cleanzip_square.png"))
        if os.path.exists(logo_png):
            try:
                from PIL import Image
                pil_logo = Image.open(logo_png)
                self.logo_image = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(42, 42))
                self.logo_label = ctk.CTkLabel(self.title_box, text="", image=self.logo_image)
                self.logo_label.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        self.title_label = ctk.CTkLabel(
            self.title_box,
            text="CleanZip",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=("gray10", "#38BDF8"),
        )
        self.title_label.pack(side="left")

        self.badge_label = ctk.CTkLabel(
            self.title_box,
            text=f" v{__version__} Pro ",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="white",
            fg_color="#0284C7",
            corner_radius=6,
        )
        self.badge_label.pack(side="left", padx=(8, 0))

        self.subtitle_label = ctk.CTkLabel(
            self.header_left,
            text="Nén sạch dự án để gửi AI / backup • Tự động loại bỏ rác & bảo mật mã nguồn",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        )
        self.subtitle_label.pack(anchor="w", pady=(2, 0))

        # Theme selector ở bên phải Header
        self.header_right = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.header_right.pack(side="right", fill="y")

        self.theme_menu = ctk.CTkOptionMenu(
            self.header_right,
            values=["🌙 Tối", "☀️ Sáng", "💻 Hệ thống"],
            width=115,
            height=32,
            font=ctk.CTkFont(size=12),
            command=self._change_theme,
        )
        current_theme = self.cfg.get("theme", "Dark")
        if current_theme == "Dark":
            self.theme_menu.set("🌙 Tối")
        elif current_theme == "Light":
            self.theme_menu.set("☀️ Sáng")
        else:
            self.theme_menu.set("💻 Hệ thống")
        self.theme_menu.pack(anchor="e")

        # ---------------- INPUT CARD ----------------
        self.input_card = ctk.CTkFrame(self.main_container, corner_radius=12, fg_color=("gray90", "gray17"))
        self.input_card.pack(fill="x", padx=20, pady=8)

        self.input_title = ctk.CTkLabel(
            self.input_card,
            text="Đường dẫn thư mục dự án cần nén:",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.input_title.pack(anchor="w", padx=16, pady=(12, 6))

        # Khung chứa Entry + Dán + Duyệt + Xóa
        self.entry_frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        self.entry_frame.pack(fill="x", padx=16, pady=(0, 8))

        paste_hint = "Cmd+V" if sys.platform == "darwin" else "Ctrl+V"
        self.path_entry = ctk.CTkEntry(
            self.entry_frame,
            placeholder_text=f"Dán đường dẫn vào đây ({paste_hint} hoặc bấm 'Dán')...",
            height=40,
            font=ctk.CTkFont(size=13),
            corner_radius=8,
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.path_entry.bind("<Return>", lambda e: self.start_zip_thread())
        if sys.platform == "darwin":
            self.path_entry.bind("<Command-a>", lambda e: (self.path_entry.select_range(0, "end"), "break")[1])
            self.path_entry.bind("<Command-A>", lambda e: (self.path_entry.select_range(0, "end"), "break")[1])
        # Khi người dùng gõ/dán đường dẫn khác -> nạp danh sách loại bỏ của dự án đó
        self.path_entry.bind("<KeyRelease>", self._schedule_sync_excludes)
        self.path_entry.bind("<FocusOut>", self._schedule_sync_excludes)

        self.paste_btn = ctk.CTkButton(
            self.entry_frame,
            text="📋 Dán",
            width=65,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.paste_from_clipboard,
        )
        self.paste_btn.pack(side="left", padx=(0, 6))

        self.browse_btn = ctk.CTkButton(
            self.entry_frame,
            text="📁 Duyệt",
            width=70,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.browse_folder,
        )
        self.browse_btn.pack(side="left", padx=(0, 6))

        self.clear_btn = ctk.CTkButton(
            self.entry_frame,
            text="❌ Xóa",
            width=60,
            height=40,
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.clear_input,
        )
        self.clear_btn.pack(side="left")

        self.scan_frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        self.scan_frame.pack(fill="x", padx=16, pady=(0, 8))
        self.scan_label = ctk.CTkLabel(
            self.scan_frame,
            text="Chọn dự án để xem dung lượng.",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray70"),
        )
        self.scan_label.pack(side="left", fill="x", expand=True)
        self.scan_details_btn = ctk.CTkButton(
            self.scan_frame, text="Xem chi tiết", width=86, height=25,
            font=ctk.CTkFont(size=11), command=self.open_size_explorer,
        )
        self.scan_details_btn.pack(side="right", padx=(4, 0))
        self.scan_stop_btn = ctk.CTkButton(
            self.scan_frame, text="Dừng", width=54, height=25,
            font=ctk.CTkFont(size=11), state="disabled", command=self._cancel_quick_scan,
        )
        self.scan_stop_btn.pack(side="right")

        # Khung chứa Lịch sử gần đây + Thông tin đích đến
        self.meta_frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        self.meta_frame.pack(fill="x", padx=16, pady=(0, 8))

        # Lịch sử gần đây
        self.recent_label = ctk.CTkLabel(
            self.meta_frame,
            text="🕒 Gần đây:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray30", "gray70"),
        )
        self.recent_label.pack(side="left", padx=(0, 6))

        recent_vals = ["(Chọn dự án gần đây...)"] + [os.path.basename(p) + f" ({p})" for p in self.recent_list]
        self.recent_menu = ctk.CTkOptionMenu(
            self.meta_frame,
            values=recent_vals,
            height=28,
            width=280,
            font=ctk.CTkFont(size=12),
            command=self._on_select_recent,
        )
        self.recent_menu.pack(side="left", padx=(0, 15))
        self._refresh_recent_menu()

        # Vị trí lưu
        self.dest_info_label = ctk.CTkLabel(
            self.meta_frame,
            text=f"📦 Lưu tại: Downloads ({self.downloads_dir})",
            font=ctk.CTkFont(size=11),
            text_color=("#2563EB", "#60A5FA"),
        )
        self.dest_info_label.pack(side="left")

        # Tùy chọn Checkboxes
        self.options_frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        self.options_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.skip_media_var = ctk.BooleanVar(value=self.cfg.get("skip_media", True))
        self.skip_media_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Bỏ qua file Media (Video & Audio)",
            variable=self.skip_media_var,
            font=ctk.CTkFont(size=12),
            command=self._save_options,
        )
        self.skip_media_cb.pack(side="left", padx=(0, 20))
        self.auto_scan_var = ctk.BooleanVar(value=self.cfg.get("auto_scan", True))
        self.auto_scan_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Tự phân tích dung lượng",
            variable=self.auto_scan_var,
            font=ctk.CTkFont(size=12),
            command=self._save_options,
        )
        self.auto_scan_cb.pack(side="left", padx=(0, 20))

        self.auto_open_var = ctk.BooleanVar(value=self.cfg.get("auto_open", True))
        self.auto_open_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Tự động mở Downloads khi nén xong",
            variable=self.auto_open_var,
            font=ctk.CTkFont(size=12),
            command=self._save_options,
        )
        self.auto_open_cb.pack(side="left")

        # ---------------- EXCLUDE CARD ----------------
        self.exclude_card = ctk.CTkFrame(self.main_container, corner_radius=12, fg_color=("gray90", "gray17"))
        self.exclude_card.pack(fill="x", padx=20, pady=8)

        self.exclude_header = ctk.CTkFrame(self.exclude_card, fg_color="transparent")
        self.exclude_header.pack(fill="x", padx=16, pady=(12, 6))

        self.exclude_title = ctk.CTkLabel(
            self.exclude_header,
            text="🚫 Loại bỏ thêm khỏi file zip (tùy chọn)",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.exclude_title.pack(side="left")

        self.exclude_count_label = ctk.CTkLabel(
            self.exclude_header,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#2563EB", "#60A5FA"),
        )
        self.exclude_count_label.pack(side="right")

        self.exclude_btns = ctk.CTkFrame(self.exclude_card, fg_color="transparent")
        self.exclude_btns.pack(fill="x", padx=16, pady=(0, 8))

        self.size_btn = ctk.CTkButton(
            self.exclude_btns,
            text="📊 Xem dung lượng & chọn",
            width=164,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            corner_radius=8,
            command=self.open_size_explorer,
        )
        self.size_btn.pack(side="left", padx=(0, 6))

        self.edit_rules_btn = ctk.CTkButton(
            self.exclude_btns,
            text="📝 Sửa luật loại trừ",
            width=126,
            height=34,
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.open_excludes_file,
        )
        self.edit_rules_btn.pack(side="left", padx=(0, 6))

        self.add_folder_btn = ctk.CTkButton(
            self.exclude_btns,
            text="📁 Thêm thư mục",
            width=116,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.add_exclude_folder,
        )
        self.add_folder_btn.pack(side="left", padx=(0, 6))

        self.add_file_btn = ctk.CTkButton(
            self.exclude_btns,
            text="📄 Thêm file",
            width=95,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.add_exclude_files,
        )
        self.add_file_btn.pack(side="left", padx=(0, 6))

        self.clear_excl_btn = ctk.CTkButton(
            self.exclude_btns,
            text="🗑 Xóa hết",
            width=80,
            height=34,
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.clear_excludes,
        )
        self.clear_excl_btn.pack(side="left")

        self.exclude_list = ctk.CTkFrame(self.exclude_card, corner_radius=8, fg_color=("gray84", "gray13"))
        self.exclude_list.pack(fill="x", padx=16, pady=(0, 12))
        self._render_excludes()

        # ---------------- ACTION BUTTON ----------------
        self.zip_btn = ctk.CTkButton(
            self.main_container,
            text="⚡ NÉN DỰ ÁN (ZIP)",
            height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            corner_radius=10,
            command=self.start_zip_thread,
        )
        self.zip_btn.pack(fill="x", padx=20, pady=(4, 10))

        # ---------------- PROGRESS CARD ----------------
        self.progress_card = ctk.CTkFrame(self.main_container, corner_radius=12, fg_color=("gray90", "gray17"))
        self.progress_card.pack(fill="x", padx=20, pady=4)

        self.status_label = ctk.CTkLabel(
            self.progress_card,
            text="Sẵn sàng. Hãy dán đường dẫn thư mục dự án và bấm 'NÉN DỰ ÁN'.",
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray75"),
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=16, pady=(10, 6))

        self.progress_bar = ctk.CTkProgressBar(self.progress_card, height=10, corner_radius=5)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 12))

        # ---------------- RESULT CARD ----------------
        self.result_card = ctk.CTkFrame(self.main_container, corner_radius=12, fg_color=("gray88", "#112233"))

        self.result_title = ctk.CTkLabel(
            self.result_card,
            text="🎉 Đã nén thành công và lưu vào Downloads!",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#16A34A", "#4ADE80"),
            anchor="w",
        )
        self.result_title.pack(fill="x", padx=16, pady=(12, 6))

        # Khung thống kê 3 ô hiện đại
        self.stats_grid = ctk.CTkFrame(self.result_card, fg_color="transparent")
        self.stats_grid.pack(fill="x", padx=16, pady=(0, 8))

        self.stat_box1 = ctk.CTkFrame(self.stats_grid, corner_radius=8, fg_color=("gray82", "#1E3A5F"))
        self.stat_box1.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=4)
        self.stat1_val = ctk.CTkLabel(self.stat_box1, text="--", font=ctk.CTkFont(size=13, weight="bold"))
        self.stat1_val.pack(padx=8, pady=(6, 1))
        self.stat1_sub = ctk.CTkLabel(self.stat_box1, text="Dung lượng Zip", font=ctk.CTkFont(size=11), text_color=("gray40", "gray60"))
        self.stat1_sub.pack(padx=8, pady=(0, 6))

        self.stat_box2 = ctk.CTkFrame(self.stats_grid, corner_radius=8, fg_color=("gray82", "#1E3A5F"))
        self.stat_box2.pack(side="left", fill="both", expand=True, padx=3, pady=4)
        self.stat2_val = ctk.CTkLabel(self.stat_box2, text="--", font=ctk.CTkFont(size=13, weight="bold"), text_color=("#16A34A", "#4ADE80"))
        self.stat2_val.pack(padx=8, pady=(6, 1))
        self.stat2_sub = ctk.CTkLabel(self.stat_box2, text="Tiết kiệm được", font=ctk.CTkFont(size=11), text_color=("gray40", "gray60"))
        self.stat2_sub.pack(padx=8, pady=(0, 6))

        self.stat_box3 = ctk.CTkFrame(self.stats_grid, corner_radius=8, fg_color=("gray82", "#1E3A5F"))
        self.stat_box3.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        self.stat3_val = ctk.CTkLabel(self.stat_box3, text="--", font=ctk.CTkFont(size=13, weight="bold"))
        self.stat3_val.pack(padx=8, pady=(6, 1))
        self.stat3_sub = ctk.CTkLabel(self.stat_box3, text="Số file giữ lại", font=ctk.CTkFont(size=11), text_color=("gray40", "gray60"))
        self.stat3_sub.pack(padx=8, pady=(0, 6))

        self.result_detail_label = ctk.CTkLabel(
            self.result_card,
            text="",
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w",
            text_color=("gray25", "gray80"),
        )
        self.result_detail_label.pack(fill="x", padx=16, pady=(0, 8))

        # Nút thao tác sau khi nén
        self.result_actions = ctk.CTkFrame(self.result_card, fg_color="transparent")
        self.result_actions.pack(fill="x", padx=16, pady=(0, 12))

        self.open_folder_btn = ctk.CTkButton(
            self.result_actions,
            text="📂 Mở Thư Mục Downloads",
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            corner_radius=8,
            command=self.open_downloads_folder,
        )
        self.open_folder_btn.pack(side="left", padx=(0, 8))

        self.open_zip_btn = ctk.CTkButton(
            self.result_actions,
            text="⚡ Mở File Zip",
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            corner_radius=8,
            command=self.open_zip_file,
        )
        self.open_zip_btn.pack(side="left", padx=(0, 8))

        self.copy_path_btn = ctk.CTkButton(
            self.result_actions,
            text="📋 Copy Đường Dẫn",
            height=36,
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.copy_zip_path,
        )
        self.copy_path_btn.pack(side="left", padx=(0, 8))

        self.reset_btn = ctk.CTkButton(
            self.result_actions,
            text="🔄 Nén Dự Án Khác",
            height=36,
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.reset_form,
        )
        self.reset_btn.pack(side="left")

        self.after(200, self._auto_check_clipboard)

    def _change_theme(self, choice):
        if "Tối" in choice:
            ctk.set_appearance_mode("Dark")
            self.cfg["theme"] = "Dark"
        elif "Sáng" in choice:
            ctk.set_appearance_mode("Light")
            self.cfg["theme"] = "Light"
        else:
            ctk.set_appearance_mode("System")
            self.cfg["theme"] = "System"
        save_config(self.cfg)
        if self.size_explorer is not None and self.size_explorer.winfo_exists():
            self.size_explorer.style_tree()

    def _save_options(self):
        self.cfg["skip_media"] = self.skip_media_var.get()
        self.cfg["auto_open"] = self.auto_open_var.get()
        self.cfg["auto_scan"] = self.auto_scan_var.get()
        save_config(self.cfg)
        self.scan_cache = None
        if self.auto_scan_var.get():
            self._schedule_quick_scan()
        else:
            self._invalidate_quick_scan()
            self.scan_label.configure(text="Tự phân tích dung lượng đang tắt.")
            self.scan_stop_btn.configure(state="disabled")

    def _on_select_recent(self, choice):
        path = self._recent_map.get(choice)
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)
            self._sync_project_excludes()
            self._schedule_quick_scan()
            self.status_label.configure(
                text=f"Đã chọn dự án từ lịch sử: {os.path.basename(path)}",
                text_color=("gray30", "gray75"),
            )

    def _refresh_recent_menu(self):
        self._recent_map = {}
        labels = ["(Chọn dự án gần đây...)"]
        for path in self.recent_list:
            label = f"{os.path.basename(path)} ({path})"
            self._recent_map[label] = path
            labels.append(label)
        if hasattr(self, "recent_menu"):
            self.recent_menu.configure(values=labels)

    def _add_to_history(self, path):
        path = os.path.normpath(path)
        if path in self.recent_list:
            self.recent_list.remove(path)
        self.recent_list.insert(0, path)
        self.recent_list = self.recent_list[:5]
        self.cfg["history"] = self.recent_list
        save_config(self.cfg)

        self._refresh_recent_menu()

    def _auto_check_clipboard(self):
        try:
            cb = self.clipboard_get().strip().strip('"').strip("'")
            if os.path.isdir(cb) and not self.path_entry.get().strip():
                self.path_entry.insert(0, cb)
                self._sync_project_excludes()
                self._schedule_quick_scan()
                self.status_label.configure(text=f"Đã tự động nhận diện thư mục từ clipboard: {os.path.basename(cb)}")
        except Exception:
            pass

    def paste_from_clipboard(self):
        try:
            content = self.clipboard_get().strip().strip('"').strip("'")
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, content)
            self._sync_project_excludes()
            self._schedule_quick_scan()
            if os.path.isdir(content):
                self.status_label.configure(
                    text=f"Đã dán: {os.path.basename(content)}",
                    text_color=("gray30", "gray75"),
                )
            else:
                self.status_label.configure(
                    text="Cảnh báo: Đường dẫn vừa dán không phải là thư mục hợp lệ!",
                    text_color=("#DC2626", "#F87171"),
                )
        except Exception as e:
            messagebox.showwarning("Clipboard", f"Không thể lấy nội dung clipboard: {e}")

    def browse_folder(self):
        initial = self.path_entry.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(initialdir=initial, title="Chọn thư mục dự án cần nén")
        if selected:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, os.path.normpath(selected))
            self._sync_project_excludes()
            self._schedule_quick_scan()
            self.status_label.configure(
                text=f"Đã chọn: {os.path.basename(selected)}",
                text_color=("gray30", "gray75"),
            )

    # ------------------------------------------------------------------
    # Loại bỏ thêm: chọn thư mục / file cụ thể
    # ------------------------------------------------------------------
    def _current_project(self):
        """Đường dẫn tuyệt đối của dự án đang nhập trong ô path, hoặc None nếu chưa hợp lệ."""
        p = self.path_entry.get().strip().strip('"').strip("'")
        return os.path.abspath(p) if p and os.path.isdir(p) else None

    @staticmethod
    def _project_key(project: str) -> str:
        return os.path.normcase(os.path.normpath(project))

    def _schedule_sync_excludes(self, _event=None):
        # Debounce: chờ người dùng gõ/dán xong rồi mới nạp danh sách
        if self._sync_job is not None:
            try:
                self.after_cancel(self._sync_job)
            except Exception:
                pass
        self._sync_job = self.after(350, self._sync_project_excludes)
        self._schedule_quick_scan()

    def _invalidate_quick_scan(self):
        self._scan_gen += 1
        self._scan_cancel.set()
        if self._scan_job is not None:
            try:
                self.after_cancel(self._scan_job)
            except Exception:
                pass
            self._scan_job = None

    def _schedule_quick_scan(self):
        self._invalidate_quick_scan()
        if not self.cfg.get("auto_scan", True):
            return
        if not self._current_project():
            self.scan_cache = None
            self.scan_label.configure(text="Chọn dự án để xem dung lượng.")
            self.scan_stop_btn.configure(state="disabled")
            return
        self.scan_label.configure(text="Chuẩn bị phân tích dung lượng…")
        self._scan_job = self.after(600, self._start_quick_scan)

    def _start_quick_scan(self):
        self._scan_job = None
        project = self._current_project()
        if not project or not self.cfg.get("auto_scan", True):
            return
        self._scan_cancel = threading.Event()
        cancel = self._scan_cancel
        gen = self._scan_gen
        include_media = not self.skip_media_var.get()
        self.scan_stop_btn.configure(state="normal")
        self.scan_label.configure(text="Đang phân tích dung lượng…")

        def work():
            try:
                matcher = ExcludeMatcher(build_patterns(include_media=include_media))
                root, top_files = scan_tree(
                    project, matcher, cancel=cancel,
                    progress=lambda count, rel: self._scan_q.put((gen, "progress", count, rel)),
                )
                self._scan_q.put((gen, "done", project, include_media, root, top_files))
            except Exception as exc:
                self._scan_q.put((gen, "error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        if self._scan_poll_job is None:
            self._scan_poll_job = self.after(100, self._poll_quick_scan)

    def _poll_quick_scan(self):
        self._scan_poll_job = None
        try:
            while True:
                gen, kind, *data = self._scan_q.get_nowait()
                if gen != self._scan_gen:
                    continue
                if kind == "progress":
                    self.scan_label.configure(text=f"Đang phân tích… {data[0]:,} mục · {data[1] or '.'}")
                elif kind == "done":
                    project, include_media, root, top_files = data
                    self.scan_stop_btn.configure(state="disabled")
                    if root is None:
                        self.scan_label.configure(text="Đã dừng phân tích dung lượng.")
                        continue
                    self.scan_cache = {
                        "key": project,
                        "include_media": include_media,
                        "data": (root, top_files),
                    }
                    heavy_count, stack = 0, list(root.children)
                    while stack:
                        node = stack.pop()
                        if node.kept_size >= 50 * 1024 ** 2:
                            heavy_count += 1
                        stack.extend(node.children)
                    self.scan_label.configure(
                        text=(f"📊 Tổng {human_size(root.size)} · Sẽ nén ≈ {human_size(root.kept_size)} · "
                              f"{heavy_count} thư mục ≥ 50 MB (byte gốc, chưa nén zip).")
                    )
                elif kind == "error":
                    self.scan_stop_btn.configure(state="disabled")
                    self.scan_label.configure(text=f"Không thể phân tích dung lượng: {data[0]}")
        except queue.Empty:
            pass
        if self._scan_job is None and not self._scan_cancel.is_set():
            if self.scan_label.cget("text").startswith("Đang phân tích"):
                self._scan_poll_job = self.after(100, self._poll_quick_scan)

    def _cancel_quick_scan(self):
        self._invalidate_quick_scan()
        self.scan_stop_btn.configure(state="disabled")
        self.scan_label.configure(text="Đã dừng phân tích dung lượng.")

    def open_size_explorer(self):
        if self.is_zipping:
            return
        project = self._require_project()
        if not project:
            return
        if self.size_explorer is not None and self.size_explorer.winfo_exists():
            self.size_explorer.lift()
            self.size_explorer.focus_force()
            return
        project = os.path.abspath(project)
        include_media = not self.skip_media_var.get()
        cached_result = self.scan_cache
        cached = cached_result["data"] if (
            cached_result
            and cached_result["key"] == project
            and cached_result["include_media"] == include_media
        ) else None
        self.size_explorer = SizeExplorer(self, project, include_media=include_media, cached=cached)

    def open_excludes_file(self):
        target = USER_EXCLUDES_FILE
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not os.path.isfile(target):
                shutil.copyfile(PACKAGED_EXCLUDES_FILE, target)
            if sys.platform == "win32":
                os.startfile(target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
            self.status_label.configure(text=f"Đang mở luật loại trừ: {target}")
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("Không thể mở file", f"Không mở được file luật loại trừ:\n{target}\n\n{exc}")

    def _sync_project_excludes(self):
        """Nạp danh sách loại bỏ đã lưu của dự án đang chọn (mỗi dự án có danh sách riêng)."""
        self._sync_job = None
        project = self._current_project()
        key = self._project_key(project) if project else None
        if key == self.excl_key:
            return
        if self.size_explorer is not None and self.size_explorer.winfo_exists():
            self.size_explorer._on_close()
        self.excl_key = key
        store = self.cfg.get("project_excludes")
        saved = store.get(key, []) if (key and isinstance(store, dict)) else []
        self.excl_items = [
            {"path": i["path"], "kind": i.get("kind", "file")}
            for i in saved
            if isinstance(i, dict) and isinstance(i.get("path"), str) and i["path"]
        ]
        self._render_excludes()

    def _persist_excludes(self):
        if not self.excl_key:
            return
        store = self.cfg.get("project_excludes")
        if not isinstance(store, dict):
            store = {}
        store.pop(self.excl_key, None)  # bỏ rồi thêm lại để dự án này nằm cuối = mới dùng nhất
        if self.excl_items:
            store[self.excl_key] = list(self.excl_items)
        while len(store) > 30:  # chỉ nhớ tối đa 30 dự án
            store.pop(next(iter(store)))
        self.cfg["project_excludes"] = store
        save_config(self.cfg)

    def _render_excludes(self):
        for w in self.exclude_list.winfo_children():
            w.destroy()

        n = len(self.excl_items)
        if n == 0:
            self.exclude_count_label.configure(text="")
            self.clear_excl_btn.configure(state="disabled")
            ctk.CTkLabel(
                self.exclude_list,
                text="Chưa chọn mục nào. Các thư mục/file rác mặc định vẫn được loại tự động.",
                font=ctk.CTkFont(size=12),
                text_color=("gray40", "gray60"),
                anchor="w",
            ).pack(fill="x", padx=12, pady=10)
            if self.size_explorer is not None and self.size_explorer.winfo_exists():
                self.size_explorer.refresh_status()
            return

        self.exclude_count_label.configure(text=f"{n} mục đã chọn")
        self.clear_excl_btn.configure(state="normal")
        project = self._current_project()

        for idx, item in enumerate(self.excl_items):
            row = ctk.CTkFrame(self.exclude_list, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=(6 if idx == 0 else 1, 6 if idx == n - 1 else 1))

            # Nút xóa pack trước (side=right) để không bị đẩy mất khi đường dẫn dài
            ctk.CTkButton(
                row,
                text="✖",
                width=28,
                height=24,
                font=ctk.CTkFont(size=12),
                fg_color="transparent",
                hover_color=("gray72", "gray28"),
                text_color=("#DC2626", "#F87171"),
                command=lambda p=item["path"]: self.remove_exclude(p),
            ).pack(side="right")

            is_dir = item["kind"] == "dir"
            exists = bool(project) and os.path.lexists(os.path.join(project, item["path"]))
            label = f"{'📁' if is_dir else '📄'}  {_shorten(item['path'])}{'/' if is_dir else ''}"
            if not exists:
                label += "   ⚠️ không còn tồn tại"
            ctk.CTkLabel(
                row,
                text=label,
                font=ctk.CTkFont(size=12),
                text_color=("gray25", "gray80") if exists else ("#B45309", "#FBBF24"),
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(6, 4))

        if self.size_explorer is not None and self.size_explorer.winfo_exists():
            self.size_explorer.refresh_status()

    def _require_project(self):
        project = self._current_project()
        self._sync_project_excludes()
        if not project:
            messagebox.showinfo(
                "Chưa chọn dự án",
                "Hãy dán hoặc chọn thư mục dự án ở trên trước,\nrồi mới chọn các thư mục/file cần loại bỏ.",
            )
        return project

    def add_exclude_folder(self):
        if self.is_zipping:
            return
        project = self._require_project()
        if not project:
            return
        selected = filedialog.askdirectory(initialdir=project, title="Chọn thư mục muốn loại bỏ khỏi file zip")
        if selected:
            self._add_excludes([selected])

    def add_exclude_files(self):
        if self.is_zipping:
            return
        project = self._require_project()
        if not project:
            return
        selected = filedialog.askopenfilenames(initialdir=project, title="Chọn file muốn loại bỏ khỏi file zip (chọn được nhiều file)")
        if selected:
            self._add_excludes(list(selected))

    def _add_excludes(self, paths):
        project = self._current_project()
        if not project:
            return

        added, skipped_dup, outside = [], 0, []
        for raw in paths:
            raw = os.path.normpath(raw)
            rel_set, invalid, _missing = resolve_exclude_paths(project, [raw])
            if invalid or not rel_set:
                outside.append(raw)
                continue

            rel = os.path.relpath(raw, project).replace("\\", "/")
            key = _nk(rel)

            # Trùng, hoặc đã nằm trong 1 thư mục đang bị loại -> không cần thêm
            already = any(
                key == _nk(it["path"]) or (it["kind"] == "dir" and key.startswith(_nk(it["path"]) + "/"))
                for it in self.excl_items
            )
            if already:
                skipped_dup += 1
                continue

            kind = "dir" if os.path.isdir(raw) else "file"
            if kind == "dir":
                # Thư mục mới bao trùm các mục con đã chọn trước đó -> gộp lại cho gọn
                self.excl_items = [it for it in self.excl_items if not _nk(it["path"]).startswith(key + "/")]
            self.excl_items.append({"path": rel, "kind": kind})
            added.append(rel)

        self.excl_items.sort(key=lambda it: (it["kind"] != "dir", _nk(it["path"])))
        self._persist_excludes()
        self._render_excludes()

        msg = f"Đã thêm {len(added)} mục vào danh sách loại bỏ." if added else "Không có mục nào được thêm."
        if skipped_dup:
            msg += f" ({skipped_dup} mục đã có sẵn hoặc đã nằm trong thư mục bị loại)"
        self.status_label.configure(text=msg, text_color=("gray30", "gray75"))

        if outside:
            shown = "\n".join(f"• {_shorten(o, 80)}" for o in outside[:5])
            more = f"\n... và {len(outside) - 5} mục khác" if len(outside) > 5 else ""
            messagebox.showwarning(
                "Mục nằm ngoài dự án",
                f"Các mục sau nằm NGOÀI thư mục dự án (hoặc chính là thư mục gốc) nên đã bị bỏ qua:\n\n{shown}{more}",
            )

    def remove_exclude(self, rel_path: str):
        if self.is_zipping:
            return
        self.excl_items = [it for it in self.excl_items if it["path"] != rel_path]
        self._persist_excludes()
        self._render_excludes()

    def clear_excludes(self):
        if self.is_zipping or not self.excl_items:
            return
        self.excl_items = []
        self._persist_excludes()
        self._render_excludes()
        self.status_label.configure(text="Đã xóa toàn bộ danh sách loại bỏ thêm.", text_color=("gray30", "gray75"))

    def _set_exclude_controls(self, state: str):
        self.size_btn.configure(state=state)
        self.add_folder_btn.configure(state=state)
        self.add_file_btn.configure(state=state)
        if state == "normal" and not self.excl_items:
            self.clear_excl_btn.configure(state="disabled")
        else:
            self.clear_excl_btn.configure(state=state)
        if self.size_explorer is not None and self.size_explorer.winfo_exists():
            self.size_explorer.refresh_status()

    def clear_input(self):
        self.path_entry.delete(0, "end")
        self._sync_project_excludes()
        self._schedule_quick_scan()
        self.path_entry.focus()
        self.status_label.configure(text="Đã xóa ô nhập. Hãy dán hoặc chọn đường dẫn mới.", text_color=("gray30", "gray75"))

    def reset_form(self):
        self.result_card.pack_forget()
        self.path_entry.delete(0, "end")
        self._sync_project_excludes()
        self._schedule_quick_scan()
        self.path_entry.focus()
        self.progress_bar.set(0)
        self.status_label.configure(text="Sẵn sàng. Hãy dán đường dẫn thư mục dự án và bấm 'NÉN DỰ ÁN'.", text_color=("gray30", "gray75"))

    def start_zip_thread(self):
        if self.is_zipping:
            return

        source = self.path_entry.get().strip().strip('"').strip("'")
        if not source:
            messagebox.showwarning("Chưa nhập đường dẫn", "Vui lòng dán hoặc chọn đường dẫn thư mục dự án cần nén!")
            self.path_entry.focus()
            return

        if not os.path.isdir(source):
            messagebox.showerror("Thư mục không tồn tại", f"Không tìm thấy thư mục:\n{source}\n\nVui lòng kiểm tra lại đường dẫn!")
            return

        self.result_card.pack_forget()

        # Đảm bảo danh sách loại bỏ khớp đúng dự án đang nhập (phòng khi vừa gõ xong bấm nén ngay)
        self._sync_project_excludes()
        exclude_paths = [it["path"] for it in self.excl_items]

        self.is_zipping = True
        self._cancel_event = threading.Event()
        self.zip_btn.configure(state="normal", text="⏹ HỦY", command=self._cancel_zip)
        self.paste_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        self._set_exclude_controls("disabled")
        self.progress_bar.set(0)
        self.status_label.configure(
            text="Đang bắt đầu quét các file và thư mục...",
            text_color=("gray30", "gray75"),
        )

        skip_media = self.skip_media_var.get()
        include_media = not skip_media

        thread = threading.Thread(target=self._run_zip, args=(source, include_media, exclude_paths), daemon=True)
        thread.start()
        self.after(80, self._poll_zip)

    def _cancel_zip(self):
        if self.is_zipping:
            self._cancel_event.set()
            self.zip_btn.configure(state="disabled", text="⏳ Đang hủy...")
            self.status_label.configure(text="Đang hủy tác vụ và dọn file ZIP tạm…")

    def _run_zip(self, source_dir: str, include_media: bool, exclude_paths=None):
        try:
            project_name = os.path.basename(source_dir.rstrip(os.sep)) or "project"
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            zip_filename = f"{project_name}_clean_{timestamp}.zip"
            output_path = os.path.join(self.downloads_dir, zip_filename)

            def on_progress(stage, current, total, message):
                self._zip_q.put(("progress", stage, current, total, message))

            start_time = time.time()
            res = zip_project(
                source_dir=source_dir,
                output_path=output_path,
                excludes_file=get_default_excludes_file(),
                include_media=include_media,
                exclude_paths=exclude_paths,
                progress_callback=on_progress,
                cancel_event=self._cancel_event,
            )
            res["manual_excluded"] = len(exclude_paths or [])
            elapsed = time.time() - start_time
            self._zip_q.put(("success", res, elapsed, source_dir))
        except ZipCancelled:
            self._zip_q.put(("cancelled",))
        except Exception as e:
            self._zip_q.put(("error", str(e)))

    def _poll_zip(self):
        try:
            while True:
                kind, *data = self._zip_q.get_nowait()
                if kind == "progress":
                    self._update_progress(*data)
                elif kind == "success":
                    res, elapsed, source_dir = data
                    self.last_zip_path = res["output_path"]
                    self._add_to_history(source_dir)
                    self._on_zip_success(res, elapsed)
                elif kind == "cancelled":
                    self._on_zip_cancelled()
                elif kind == "error":
                    self._on_zip_error(data[0])
        except queue.Empty:
            pass
        if self.is_zipping:
            self.after(80, self._poll_zip)

    def _restore_zip_controls(self):
        self.is_zipping = False
        self.zip_btn.configure(state="normal", text="⚡ NÉN DỰ ÁN (ZIP)", command=self.start_zip_thread)
        self.paste_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
        self.clear_btn.configure(state="normal")
        self._set_exclude_controls("normal")

    def _on_zip_cancelled(self):
        self._restore_zip_controls()
        self.progress_bar.set(0)
        self.status_label.configure(
            text="Đã hủy. File ZIP tạm đã được dọn sạch.",
            text_color=("gray30", "gray75"),
        )

    def _update_progress(self, stage, current, total, message):
        self.status_label.configure(text=message, text_color=("gray30", "gray75"))
        if stage == "scan":
            self.progress_bar.set(0.1)
        elif stage == "compress" and total > 0:
            fraction = min(max(current / total, 0.1), 0.99)
            self.progress_bar.set(fraction)
        elif stage == "done":
            self.progress_bar.set(1.0)

    def _on_zip_success(self, res: dict, elapsed: float):
        self._restore_zip_controls()
        self.progress_bar.set(1.0)

        out_name = os.path.basename(res["output_path"])
        zip_size_str = human_size(res["compressed_size"])
        skipped_size_str = human_size(res["skipped_size"])
        kept_size_str = human_size(res["kept_size"])

        # Cập nhật 3 ô thống kê
        self.stat1_val.configure(text=zip_size_str)
        self.stat1_sub.configure(text=f"Gốc: ~{kept_size_str}")

        self.stat2_val.configure(text=f"~{skipped_size_str}")
        self.stat2_sub.configure(text=f"{res['skipped_dirs_count']} thư mục, {res['skipped_files_count']} file bị loại")

        self.stat3_val.configure(text=f"{res['kept_count']} files")
        self.stat3_sub.configure(text=f"Thời gian: {elapsed:.1f}s")

        detail_text = f"• File kết quả: {out_name}\n• Vị trí: {res['output_path']}"
        if res.get("manual_excluded"):
            detail_text += f"\n• Loại bỏ thêm theo lựa chọn của bạn: {res['manual_excluded']} mục"
        if res.get("skipped_symlinks"):
            detail_text += f"\n• Bỏ qua {res['skipped_symlinks']} liên kết tượng trưng (symlink)"
        if res.get("missing_exclude_paths"):
            detail_text += f"\n⚠️ {len(res['missing_exclude_paths'])} mục bạn chọn không còn tồn tại trong dự án nên không có tác dụng."
        if res.get("failed_count"):
            detail_text += f"\n⚠️ Lưu ý: Có {res['failed_count']} file bị bỏ qua do lỗi quyền truy cập / file đang bị khóa."
        self.result_detail_label.configure(text=detail_text)

        self.status_label.configure(text="✅ Hoàn tất! File zip đã sẵn sàng trong Downloads.", text_color=("#16A34A", "#4ADE80"))
        self.result_card.pack(fill="x", padx=20, pady=(6, 10))
        self.after(150, self._scroll_to_bottom)

        # Tự động mở Downloads nếu bật tùy chọn
        if self.auto_open_var.get():
            self.after(300, self.open_downloads_folder)

    def _on_zip_error(self, err_msg: str):
        self._restore_zip_controls()
        self.progress_bar.set(0)
        self.status_label.configure(
            text=f"❌ Có lỗi xảy ra: {err_msg}",
            text_color=("#DC2626", "#F87171"),
        )
        messagebox.showerror("Lỗi Nén", f"Đã xảy ra lỗi trong quá trình nén dự án:\n\n{err_msg}")

    def _scroll_to_bottom(self):
        """Cuộn xuống cuối để thấy khung kết quả khi cửa sổ nhỏ."""
        try:
            self.main_container._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def open_downloads_folder(self):
        if self.last_zip_path and os.path.exists(self.last_zip_path):
            if sys.platform == "win32":
                subprocess.Popen(f'explorer /select,"{os.path.normpath(self.last_zip_path)}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", self.last_zip_path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(self.last_zip_path)])
        else:
            if sys.platform == "win32":
                subprocess.Popen(f'explorer "{os.path.normpath(self.downloads_dir)}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.downloads_dir])
            else:
                subprocess.Popen(["xdg-open", self.downloads_dir])

    def open_zip_file(self):
        if self.last_zip_path and os.path.exists(self.last_zip_path):
            try:
                if sys.platform == "win32":
                    os.startfile(os.path.normpath(self.last_zip_path))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", self.last_zip_path])
                else:
                    subprocess.Popen(["xdg-open", self.last_zip_path])
            except Exception as e:
                messagebox.showinfo("Thông báo", f"Không thể mở trực tiếp: {e}")

    def copy_zip_path(self):
        if self.last_zip_path:
            self.clipboard_clear()
            self.clipboard_append(os.path.normpath(self.last_zip_path))
            self.status_label.configure(text="📋 Đã copy đường dẫn file zip vào clipboard!")


def main():
    app = CleanZipApp()
    app.mainloop()


if __name__ == "__main__":
    main()
