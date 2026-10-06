#!/usr/bin/env python3
"""Tree-based folder size explorer used by the CleanZip desktop application."""

import os
import queue
import subprocess
import sys
import threading
from tkinter import Menu, ttk

import customtkinter as ctk

from cleanzip import ExcludeMatcher, build_patterns, human_size, scan_tree

HEAVY = 50 * 1024 ** 2
WARN = 10 * 1024 ** 2
MAX_ROWS = 300
TOP_N = 30


def nk(rel):
    return os.path.normcase(rel).replace("\\", "/").strip("/")


class SizeExplorer(ctk.CTkToplevel):
    def __init__(self, app, project, include_media=False, cached=None):
        super().__init__(app)
        self.app, self.project, self.include_media = app, project, include_media
        self.title(f"Phân tích dung lượng - {os.path.basename(project) or project}")
        self.geometry("940x640")
        self.minsize(780, 480)
        self.q, self.cancel, self.gen = queue.Queue(), threading.Event(), 0
        self.matcher = ExcludeMatcher(build_patterns(include_media=include_media))
        self.root_node, self.top_files, self.by_iid = None, [], {}
        self._poll_job = None
        self._build_ui()
        self.style_tree()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if cached:
            self._show(*cached)
        else:
            self.rescan()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.summary = ctk.CTkLabel(top, text="Đang quét…", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.summary.pack(side="left", fill="x", expand=True)
        self.rescan_btn = ctk.CTkButton(top, text="🔄 Quét lại", width=90, command=self.rescan)
        self.rescan_btn.pack(side="right")

        self.seg = ctk.CTkSegmentedButton(self, values=["Cây thư mục", "Top thư mục", "Top file"], command=self._on_view)
        self.seg.set("Cây thư mục")
        self.seg.pack(fill="x", padx=12, pady=4)

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=4)
        cols = ("total", "kept", "bar", "files", "status")
        self.tree = ttk.Treeview(frame, columns=cols, style="Size.Treeview", selectmode="extended")
        for col, label, width, anchor in [
            ("#0", "Tên", 280, "w"), ("total", "Tổng", 85, "e"), ("kept", "Sẽ nén", 85, "e"),
            ("bar", "Tỉ trọng", 130, "w"), ("files", "File", 70, "e"), ("status", "Trạng thái", 190, "w"),
        ]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor=anchor, stretch=col in ("#0", "status"))
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for tag, color in (("heavy", "#F87171"), ("warn", "#FBBF24"), ("auto", "#6B7280"), ("manual", "#FB923C")):
            self.tree.tag_configure(tag, foreground=color)
        self.tree.bind("<<TreeviewOpen>>", self._on_open)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", self._context_menu)
        self.tree.bind("<Button-2>", self._context_menu)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=12, pady=(4, 10))
        self.sel_label = ctk.CTkLabel(bottom, text="", anchor="w")
        self.sel_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            bottom, text="Đóng", width=70, fg_color=("gray75", "gray28"), text_color=("gray10", "gray90"),
            command=self._on_close,
        ).pack(side="right")
        self.add_btn = ctk.CTkButton(bottom, text="🚫 Thêm vào danh sách loại bỏ", state="disabled", command=self._add_selected)
        self.add_btn.pack(side="right", padx=(0, 8))

    def style_tree(self):
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg, selected, heading = (
            ("#1F2937", "#E5E7EB", "#0369A1", "#111827")
            if dark else ("#FFFFFF", "#111827", "#BAE6FD", "#E5E7EB")
        )
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Size.Treeview", background=bg, fieldbackground=bg, foreground=fg, rowheight=26, borderwidth=0)
        style.map("Size.Treeview", background=[("selected", selected)], foreground=[("selected", fg)])
        style.configure("Size.Treeview.Heading", background=heading, foreground=fg, relief="flat")

    def rescan(self):
        self.cancel.set()
        self.cancel, self.gen = threading.Event(), self.gen + 1
        gen, cancel, project = self.gen, self.cancel, self.project
        include_media = self.include_media
        matcher = ExcludeMatcher(build_patterns(include_media=include_media))
        self.matcher = matcher
        self.summary.configure(text="Đang quét…")
        self.rescan_btn.configure(state="disabled")

        def work():
            try:
                result = scan_tree(
                    project, matcher, cancel=cancel, top_n=TOP_N,
                    progress=lambda count, rel: self.q.put((gen, "progress", count, rel)),
                )
                self.q.put((gen, "done", result))
            except Exception as exc:
                self.q.put((gen, "error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        if self._poll_job is None:
            self._poll_job = self.after(100, self._poll)

    def _poll(self):
        self._poll_job = None
        busy = True
        try:
            while True:
                gen, kind, *data = self.q.get_nowait()
                if gen != self.gen:
                    continue
                if kind == "progress":
                    self.summary.configure(text=f"Đang quét… {data[0]:,} mục · {data[1] or '.'}")
                elif kind == "done":
                    busy = False
                    if data[0][0] is not None:
                        self._show(*data[0])
                elif kind == "error":
                    busy = False
                    self.summary.configure(text=f"Lỗi khi quét: {data[0]}")
        except queue.Empty:
            pass
        if busy:
            self._poll_job = self.after(100, self._poll)
        else:
            self.rescan_btn.configure(state="normal")

    def _on_close(self):
        self.cancel.set()
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
        self.app.size_explorer = None
        self.destroy()

    def _show(self, root, top_files):
        self.root_node, self.top_files = root, top_files
        self.app.scan_cache = {
            "key": self.project,
            "include_media": self.include_media,
            "data": (root, top_files),
        }
        self.rescan_btn.configure(state="normal")
        self._on_view(self.seg.get())

    def _on_view(self, choice):
        self.tree.delete(*self.tree.get_children())
        self.by_iid = {}
        if not self.root_node:
            return
        if choice == "Cây thư mục":
            self._insert_children("", self.root_node)
        elif choice == "Top thư mục":
            nodes, stack = [], [self.root_node]
            while stack:
                node = stack.pop()
                if node.excluded_by:
                    continue
                if node.rel and node.own_size:
                    nodes.append(node)
                stack.extend(node.children)
            for node in sorted(nodes, key=lambda item: item.own_size, reverse=True)[:TOP_N]:
                self.by_iid[node.rel] = node
                self.tree.insert(
                    "", "end", iid=node.rel, text="📁 " + node.rel + "/",
                    values=(human_size(node.own_size), human_size(node.kept_size), self._bar(node.own_size),
                            f"{node.kept_file_count:,}", self._status(node)),
                    tags=(self._tag(node),),
                )
        else:
            for size, rel, excluded in self.top_files:
                self.tree.insert(
                    "", "end", text="📄 " + rel,
                    values=(human_size(size), "-" if excluded else human_size(size), self._bar(size), "1",
                            "Bị loại bởi luật" if excluded else "Sẽ nén"),
                    tags=("auto" if excluded else "ok",),
                )
        self.summary.configure(
            text=(f"Tổng {human_size(self.root_node.size)} · Sẽ nén (luật mặc định) "
                  f"{human_size(self.root_node.kept_size)} · {self.root_node.file_count:,} file "
                  "(byte gốc, chưa nén zip)")
        )
        self._on_select()

    def _bar(self, size):
        total = self.root_node.size or 1
        ratio = size / total
        return f"{'█' * round(ratio * 10):<10} {ratio:.0%}"

    def _is_manual(self, rel):
        key = nk(rel)
        return any(key == nk(item["path"]) or key.startswith(nk(item["path"]) + "/") for item in self.app.excl_items)

    def _is_current_project(self):
        current = self.app._current_project()
        return bool(current) and self.app._project_key(current) == self.app._project_key(self.project)

    def _status(self, node):
        if node.excluded_by:
            return f"Loại mặc định ({node.excluded_by})"
        if self._is_manual(node.rel):
            return "Đã chọn loại bỏ"
        return "Sẽ nén" if node.kept_size else "Không có gì để nén"

    def _tag(self, node):
        if node.excluded_by:
            return "auto"
        if self._is_manual(node.rel):
            return "manual"
        return "heavy" if node.kept_size >= HEAVY else "warn" if node.kept_size >= WARN else "ok"

    def _insert_children(self, parent, node):
        if parent and node.own_size:
            self.tree.insert(
                parent, "end", iid=f"{node.rel}::own", text="📄 (file nằm trực tiếp)",
                values=(human_size(node.own_size), "", self._bar(node.own_size), "", ""), tags=("ok",),
            )
        for child in node.children[:MAX_ROWS]:
            self.by_iid[child.rel] = child
            self.tree.insert(
                parent, "end", iid=child.rel, text="📁 " + child.name,
                values=(human_size(child.size), human_size(child.kept_size), self._bar(child.size),
                        f"{child.file_count:,}", self._status(child)),
                tags=(self._tag(child),),
            )
            if child.children and not child.excluded_by:
                self.tree.insert(child.rel, "end", iid=f"{child.rel}::dummy", text="…")
        remaining = node.children[MAX_ROWS:]
        if remaining:
            self.tree.insert(
                parent, "end", iid=f"{node.rel}::more", text=f"… và {len(remaining)} thư mục nhỏ khác",
                values=(human_size(sum(child.size for child in remaining)), "", "", "", ""), tags=("ok",),
            )

    def _on_open(self, _event=None):
        iid = self.tree.focus()
        children = self.tree.get_children(iid)
        if len(children) == 1 and children[0].endswith("::dummy") and iid in self.by_iid:
            self.tree.delete(children[0])
            self._insert_children(iid, self.by_iid[iid])

    def selected_nodes(self):
        nodes = [self.by_iid[iid] for iid in self.tree.selection() if iid in self.by_iid]
        nodes = [node for node in nodes if not node.excluded_by and not self._is_manual(node.rel)]
        keys = {nk(node.rel) for node in nodes}
        return [node for node in nodes if not any(nk(node.rel).startswith(key + "/") for key in keys)]

    def _on_tree_select(self, _event=None):
        for iid in self.tree.selection():
            node = self.by_iid.get(iid)
            if node is not None and node.excluded_by:
                self.tree.selection_remove(iid)
        self._on_select()

    def _manual_removed(self, within=None):
        directory_keys = {nk(item["path"]) for item in self.app.excl_items if item.get("kind") == "dir"}
        total, stack = 0, [within or self.root_node]
        while stack:
            node = stack.pop()
            for child in node.children:
                if child.excluded_by:
                    continue
                if nk(child.rel) in directory_keys:
                    total += child.kept_size
                else:
                    stack.append(child)
        for item in self.app.excl_items:
            if item.get("kind") != "file":
                continue
            rel = item["path"].replace("\\", "/")
            key = nk(rel)
            if within is not None:
                within_key = nk(within.rel)
                if not (key == within_key or key.startswith(within_key + "/")):
                    continue
            if any(key.startswith(directory + "/") for directory in directory_keys):
                continue
            path = os.path.join(self.project, *rel.split("/"))
            if os.path.islink(path) or self.matcher(os.path.basename(rel), rel):
                continue
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        return total

    def _on_select(self):
        if not self.root_node:
            return
        nodes = self.selected_nodes()
        extra = sum(max(0, node.kept_size - self._manual_removed(node)) for node in nodes)
        base = self.root_node.kept_size - self._manual_removed()
        if nodes:
            text = (f"Đã chọn {len(nodes)} mục · bỏ thêm ≈ {human_size(extra)} · "
                    f"còn lại ≈ {human_size(base - extra)} (chưa nén zip)")
        else:
            text = f"Sẽ nén ≈ {human_size(base)} (chưa nén zip). Chọn thư mục rồi bấm 'Thêm vào danh sách loại bỏ'."
        self.sel_label.configure(text=text)
        self.add_btn.configure(
            state="normal" if nodes and not self.app.is_zipping and self._is_current_project() else "disabled"
        )

    def _add_selected(self):
        nodes = self.selected_nodes()
        if nodes and not self.app.is_zipping and self._is_current_project():
            self.app._add_excludes([os.path.join(self.project, *node.rel.split("/")) for node in nodes])
            self.refresh_status()

    def refresh_status(self):
        if not self.root_node:
            return
        for iid, node in self.by_iid.items():
            if self.tree.exists(iid):
                values = list(self.tree.item(iid, "values"))
                values[4] = self._status(node)
                self.tree.item(iid, values=values, tags=(self._tag(node),))
        self._on_select()

    def _context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self.by_iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        path = os.path.join(self.project, *self.by_iid[iid].rel.split("/"))
        menu = Menu(self, tearoff=0)
        menu.add_command(label="🚫 Thêm vào danh sách loại bỏ", command=self._add_selected)
        menu.add_command(label="📂 Mở trong trình quản lý file", command=lambda: self._reveal(path))
        menu.add_command(label="📋 Copy đường dẫn", command=lambda: self._copy_path(path))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_path(self, path):
        self.clipboard_clear()
        self.clipboard_append(path)

    @staticmethod
    def _reveal(path):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
