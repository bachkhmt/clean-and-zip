#!/usr/bin/env python3
"""
CleanZip Desktop UI
Giao diện trực quan, hiện đại cho tool CleanZip.
Cho phép copy paste đường dẫn thư mục, tự động nén sạch và lưu vào thư mục Downloads.
"""

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

# Cấu hình giao diện CustomTkinter
ctk.set_appearance_mode("Dark")  # Options: "System", "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue", "dark-blue", "green"


class CleanZipApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("CleanZip - Nén Dự Án Gọn Sạch")
        self.geometry("720x620")
        self.minsize(680, 580)

        # Đặt icon nếu có hoặc cấu hình window
        if sys.platform == "win32":
            try:
                # Bật DPI awareness tốt hơn trên Windows
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        self.downloads_dir = get_downloads_folder()
        self.is_zipping = False
        self.last_zip_path = None

        self._build_ui()

    def _build_ui(self):
        # Container chính với padding
        self.main_container = ctk.CTkFrame(self, corner_radius=16, fg_color=("gray95", "gray12"))
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # ---------------- HEADER ----------------
        self.header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=25, pady=(20, 10))

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="⚡ CleanZip",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=("gray10", "#38BDF8"),
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            self.header_frame,
            text="Nén dự án sạch để gửi AI / backup • Tự động bỏ qua node_modules, .git, venv, cache...",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray60"),
        )
        self.subtitle_label.pack(anchor="w", pady=(2, 0))

        # ---------------- INPUT CARD ----------------
        self.input_card = ctk.CTkFrame(self.main_container, corner_radius=12, fg_color=("gray90", "gray17"))
        self.input_card.pack(fill="x", padx=25, pady=12)

        self.input_title = ctk.CTkLabel(
            self.input_card,
            text="Đường dẫn thư mục dự án cần nén:",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.input_title.pack(anchor="w", padx=16, pady=(14, 6))

        # Khung chứa Entry + Nút Dán + Nút Chọn
        self.entry_frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        self.entry_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.path_entry = ctk.CTkEntry(
            self.entry_frame,
            placeholder_text=r"Dán đường dẫn vào đây (ví dụ: D:\projects\my-app)...",
            height=42,
            font=ctk.CTkFont(size=13),
            corner_radius=8,
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.path_entry.bind("<Return>", lambda e: self.start_zip_thread())

        # Nút Dán nhanh từ clipboard
        self.paste_btn = ctk.CTkButton(
            self.entry_frame,
            text="📋 Dán",
            width=70,
            height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.paste_from_clipboard,
        )
        self.paste_btn.pack(side="left", padx=(0, 8))

        # Nút Duyệt thư mục
        self.browse_btn = ctk.CTkButton(
            self.entry_frame,
            text="📁 Duyệt",
            width=75,
            height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.browse_folder,
        )
        self.browse_btn.pack(side="left")

        # Dòng thông tin thư mục Downloads đích
        self.dest_info_frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        self.dest_info_frame.pack(fill="x", padx=16, pady=(0, 12))

        self.dest_icon_label = ctk.CTkLabel(
            self.dest_info_frame,
            text="📦 Lưu tại:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray30", "gray70"),
        )
        self.dest_icon_label.pack(side="left", padx=(0, 5))

        self.dest_path_label = ctk.CTkLabel(
            self.dest_info_frame,
            text=f"{self.downloads_dir} (Thư mục Downloads)",
            font=ctk.CTkFont(size=12),
            text_color=("#2563EB", "#60A5FA"),
        )
        self.dest_path_label.pack(side="left")

        # ---------------- ACTION BUTTON ----------------
        self.zip_btn = ctk.CTkButton(
            self.main_container,
            text="⚡ NÉN DỰ ÁN (ZIP)",
            height=50,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            corner_radius=10,
            command=self.start_zip_thread,
        )
        self.zip_btn.pack(fill="x", padx=25, pady=(5, 12))

        # ---------------- PROGRESS CARD ----------------
        self.progress_card = ctk.CTkFrame(self.main_container, corner_radius=12, fg_color=("gray90", "gray17"))
        self.progress_card.pack(fill="x", padx=25, pady=6)

        self.status_label = ctk.CTkLabel(
            self.progress_card,
            text="Sẵn sàng. Hãy dán đường dẫn thư mục dự án và bấm 'NÉN DỰ ÁN'.",
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray75"),
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=16, pady=(12, 6))

        self.progress_bar = ctk.CTkProgressBar(self.progress_card, height=10, corner_radius=5)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 14))

        # ---------------- RESULT CARD ----------------
        self.result_card = ctk.CTkFrame(self.main_container, corner_radius=12, fg_color=("gray88", "#112233"))
        # Sẽ hiển thị khi nén xong

        self.result_title = ctk.CTkLabel(
            self.result_card,
            text="🎉 Đã nén thành công và lưu vào Downloads!",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#16A34A", "#4ADE80"),
            anchor="w",
        )
        self.result_title.pack(fill="x", padx=16, pady=(12, 6))

        self.result_stats_label = ctk.CTkLabel(
            self.result_card,
            text="",
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="w",
            text_color=("gray20", "gray85"),
        )
        self.result_stats_label.pack(fill="x", padx=16, pady=(0, 10))

        # Nút mở Downloads
        self.result_actions = ctk.CTkFrame(self.result_card, fg_color="transparent")
        self.result_actions.pack(fill="x", padx=16, pady=(0, 12))

        self.open_folder_btn = ctk.CTkButton(
            self.result_actions,
            text="📂 Mở Thư Mục Downloads",
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            corner_radius=8,
            command=self.open_downloads_folder,
        )
        self.open_folder_btn.pack(side="left", padx=(0, 10))

        self.copy_path_btn = ctk.CTkButton(
            self.result_actions,
            text="📋 Copy Đường Dẫn File",
            height=38,
            font=ctk.CTkFont(size=13),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray90"),
            corner_radius=8,
            command=self.copy_zip_path,
        )
        self.copy_path_btn.pack(side="left")

        # Tự động kiểm tra clipboard khi mở app: nếu clipboard là đường dẫn thư mục hợp lệ thì gợi ý dán
        self.after(200, self._auto_check_clipboard)

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

        # Ẩn kết quả cũ
        self.result_card.pack_forget()

        # Cập nhật UI sang trạng thái nén
        self.is_zipping = True
        self.zip_btn.configure(state="disabled", text="⏳ Đang xử lý...")
        self.paste_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_label.configure(
            text="Đang bắt đầu quét các file và thư mục...",
            text_color=("gray30", "gray75"),
        )

        thread = threading.Thread(target=self._run_zip, args=(source,), daemon=True)
        thread.start()

    def _run_zip(self, source_dir: str):
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
                progress_callback=on_progress,
            )
            elapsed = time.time() - start_time

            self.last_zip_path = output_path
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
        self.progress_bar.set(1.0)

        out_name = os.path.basename(res["output_path"])
        zip_size_str = human_size(res["compressed_size"])
        skipped_size_str = human_size(res["skipped_size"])
        kept_size_str = human_size(res["kept_size"])

        stats_text = (
            f"• File: {out_name}\n"
            f"• Dung lượng zip: {zip_size_str} (tổng gốc: ~{kept_size_str})\n"
            f"• Tiết kiệm được: ~{skipped_size_str} từ {res['skipped_dirs_count']} thư mục rác (node_modules, .git,...)\n"
            f"• Giữ lại: {res['kept_count']} files • Thời gian: {elapsed:.1f}s"
        )
        self.result_stats_label.configure(text=stats_text)
        self.status_label.configure(text="✅ Hoàn tất! File zip đã sẵn sàng trong Downloads.", text_color=("#16A34A", "#4ADE80"))

        # Hiển thị result card
        self.result_card.pack(fill="x", padx=25, pady=(10, 10))

    def _on_zip_error(self, err_msg: str):
        self.is_zipping = False
        self.zip_btn.configure(state="normal", text="⚡ NÉN DỰ ÁN (ZIP)")
        self.paste_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
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
