#!/usr/bin/env python3
"""
CleanZip Desktop UI v2.1
Giao diện trực quan, hiện đại cho tool CleanZip.
Hỗ trợ dán nhanh, duyệt thư mục, lịch sử gần đây, chuyển đổi theme sáng/tối,
tùy chọn bỏ qua media, mở trực tiếp file zip và thư mục Downloads.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from cleanzip import (
    DEFAULT_EXCLUDES_FILE,
    get_downloads_folder,
    human_size,
    zip_project,
)

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".cleanzip_config.json")


def load_config():
    default_cfg = {
        "history": [],
        "theme": "Dark",
        "auto_open": True,
        "skip_media": True,
    }
    try:
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
    except Exception:
        pass
    return default_cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_resource_path(relative_path: str) -> str:
    """Lấy đường dẫn tài nguyên tuyệt đối, tương thích cả khi chạy source code và khi đóng gói PyInstaller."""
    if getattr(sys, "frozen", False):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class CleanZipApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.cfg = load_config()
        theme_mode = self.cfg.get("theme", "Dark")
        ctk.set_appearance_mode(theme_mode)
        ctk.set_default_color_theme("blue")

        self.title("CleanZip Desktop v2.1 - Nén Dự Án Gọn Sạch")
        self.geometry("760x690")
        self.minsize(720, 640)

        # Cấu hình icon cửa sổ và thanh tác vụ Windows
        if sys.platform == "win32":
            try:
                from ctypes import windll
                # 1. Định danh AppUserModelID để Windows Taskbar hiển thị icon riêng của app
                windll.shell32.SetCurrentProcessExplicitAppUserModelID("bachkhmt.cleanzip.desktop.v21")
                # 2. DPI Awareness
                windll.shcore.SetProcessDpiAwareness(1)
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

        self._build_ui()

    def _build_ui(self):
        self.main_container = ctk.CTkFrame(self, corner_radius=16, fg_color=("gray95", "gray12"))
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
            text=" v2.1 Pro ",
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

        self.path_entry = ctk.CTkEntry(
            self.entry_frame,
            placeholder_text=r"Dán đường dẫn vào đây (Ctrl+V hoặc bấm 'Dán')...",
            height=40,
            font=ctk.CTkFont(size=13),
            corner_radius=8,
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.path_entry.bind("<Return>", lambda e: self.start_zip_thread())

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

        self.auto_open_var = ctk.BooleanVar(value=self.cfg.get("auto_open", True))
        self.auto_open_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Tự động mở Downloads khi nén xong",
            variable=self.auto_open_var,
            font=ctk.CTkFont(size=12),
            command=self._save_options,
        )
        self.auto_open_cb.pack(side="left")

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

    def _save_options(self):
        self.cfg["skip_media"] = self.skip_media_var.get()
        self.cfg["auto_open"] = self.auto_open_var.get()
        save_config(self.cfg)

    def _on_select_recent(self, choice):
        if choice and not choice.startswith("("):
            for p in self.recent_list:
                if p in choice:
                    self.path_entry.delete(0, "end")
                    self.path_entry.insert(0, p)
                    self.status_label.configure(
                        text=f"Đã chọn dự án từ lịch sử: {os.path.basename(p)}",
                        text_color=("gray30", "gray75"),
                    )
                    break

    def _add_to_history(self, path):
        path = os.path.normpath(path)
        if path in self.recent_list:
            self.recent_list.remove(path)
        self.recent_list.insert(0, path)
        self.recent_list = self.recent_list[:5]
        self.cfg["history"] = self.recent_list
        save_config(self.cfg)

        recent_vals = ["(Chọn dự án gần đây...)"] + [os.path.basename(p) + f" ({p})" for p in self.recent_list]
        self.recent_menu.configure(values=recent_vals)

    def _auto_check_clipboard(self):
        try:
            cb = self.clipboard_get().strip().strip('"').strip("'")
            if os.path.isdir(cb) and not self.path_entry.get().strip():
                self.path_entry.insert(0, cb)
                self.status_label.configure(text=f"Đã tự động nhận diện thư mục từ clipboard: {os.path.basename(cb)}")
        except Exception:
            pass

    def paste_from_clipboard(self):
        try:
            content = self.clipboard_get().strip().strip('"').strip("'")
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, content)
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
            self.status_label.configure(
                text=f"Đã chọn: {os.path.basename(selected)}",
                text_color=("gray30", "gray75"),
            )

    def clear_input(self):
        self.path_entry.delete(0, "end")
        self.path_entry.focus()
        self.status_label.configure(text="Đã xóa ô nhập. Hãy dán hoặc chọn đường dẫn mới.", text_color=("gray30", "gray75"))

    def reset_form(self):
        self.result_card.pack_forget()
        self.path_entry.delete(0, "end")
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

        self.is_zipping = True
        self.zip_btn.configure(state="disabled", text="⏳ Đang xử lý...")
        self.paste_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_label.configure(
            text="Đang bắt đầu quét các file và thư mục...",
            text_color=("gray30", "gray75"),
        )

        skip_media = self.skip_media_var.get()
        include_media = not skip_media

        thread = threading.Thread(target=self._run_zip, args=(source, include_media), daemon=True)
        thread.start()

    def _run_zip(self, source_dir: str, include_media: bool):
        try:
            project_name = os.path.basename(source_dir.rstrip(os.sep)) or "project"
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            zip_filename = f"{project_name}_clean_{timestamp}.zip"
            output_path = os.path.join(self.downloads_dir, zip_filename)

            def on_progress(stage, current, total, message):
                self.after(0, self._update_progress, stage, current, total, message)

            start_time = time.time()
            res = zip_project(
                source_dir=source_dir,
                output_path=output_path,
                excludes_file=DEFAULT_EXCLUDES_FILE,
                include_media=include_media,
                progress_callback=on_progress,
            )
            elapsed = time.time() - start_time

            self.last_zip_path = output_path
            self.after(0, self._add_to_history, source_dir)
            self.after(0, self._on_zip_success, res, elapsed)

        except Exception as e:
            self.after(0, self._on_zip_error, str(e))

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
        self.is_zipping = False
        self.zip_btn.configure(state="normal", text="⚡ NÉN DỰ ÁN (ZIP)")
        self.paste_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
        self.clear_btn.configure(state="normal")
        self.progress_bar.set(1.0)

        out_name = os.path.basename(res["output_path"])
        zip_size_str = human_size(res["compressed_size"])
        skipped_size_str = human_size(res["skipped_size"])
        kept_size_str = human_size(res["kept_size"])

        # Cập nhật 3 ô thống kê
        self.stat1_val.configure(text=zip_size_str)
        self.stat1_sub.configure(text=f"Gốc: ~{kept_size_str}")

        self.stat2_val.configure(text=f"~{skipped_size_str}")
        self.stat2_sub.configure(text=f"{res['skipped_dirs_count']} thư mục rác")

        self.stat3_val.configure(text=f"{res['kept_count']} files")
        self.stat3_sub.configure(text=f"Thời gian: {elapsed:.1f}s")

        detail_text = f"• File kết quả: {out_name}\n• Vị trí: {res['output_path']}"
        if res.get("failed_count"):
            detail_text += f"\n⚠️ Lưu ý: Có {res['failed_count']} file bị bỏ qua do lỗi quyền truy cập / file đang bị khóa."
        self.result_detail_label.configure(text=detail_text)

        self.status_label.configure(text="✅ Hoàn tất! File zip đã sẵn sàng trong Downloads.", text_color=("#16A34A", "#4ADE80"))
        self.result_card.pack(fill="x", padx=20, pady=(6, 10))

        # Tự động mở Downloads nếu bật tùy chọn
        if self.auto_open_var.get():
            self.after(300, self.open_downloads_folder)

    def _on_zip_error(self, err_msg: str):
        self.is_zipping = False
        self.zip_btn.configure(state="normal", text="⚡ NÉN DỰ ÁN (ZIP)")
        self.paste_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
        self.clear_btn.configure(state="normal")
        self.progress_bar.set(0)
        self.status_label.configure(
            text=f"❌ Có lỗi xảy ra: {err_msg}",
            text_color=("#DC2626", "#F87171"),
        )
        messagebox.showerror("Lỗi Nén", f"Đã xảy ra lỗi trong quá trình nén dự án:\n\n{err_msg}")

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
