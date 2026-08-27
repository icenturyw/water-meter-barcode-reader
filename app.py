from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageOps, ImageTk

from core import (
    STATUS_AUTO,
    STATUS_MANUAL,
    STATUS_REVIEW,
    STATUS_UNREAD,
    ScanRecord,
    ScanSettings,
    SUPPORTED_EXTENSIONS,
    apply_manual_value,
    discover_images,
    export_csv,
    export_xlsx,
    mark_duplicates,
    parse_exact_length,
    scan_image,
)


APP_NAME = "水表表号批量识别工具"
APP_VERSION = "1.0.1"


class MeterReaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1280x790")
        self.minsize(1050, 680)
        self.configure(bg="#EEF3F6")

        self.files: list[Path] = []
        self.records: list[ScanRecord] = []
        self.scan_queue: queue.Queue[tuple] = queue.Queue()
        self.cancel_event = threading.Event()
        self.scan_thread: threading.Thread | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.show_exceptions_only = tk.BooleanVar(value=False)

        self.batch_var = tk.StringVar()
        self.length_var = tk.StringVar(value="14")
        self.prefix_var = tk.StringVar()
        self.digits_only_var = tk.BooleanVar(value=True)
        self.recursive_var = tk.BooleanVar(value=True)
        self.source_var = tk.StringVar(value="尚未选择照片")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text_var = tk.StringVar(value="请选择照片文件夹或若干照片")
        self.summary_vars = {
            "total": tk.StringVar(value="0"),
            "auto": tk.StringVar(value="0"),
            "review": tk.StringVar(value="0"),
            "unread": tk.StringVar(value="0"),
            "duplicate": tk.StringVar(value="0"),
        }

        self._configure_styles()
        self._build_ui()
        self.after(100, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        default_font = ("Microsoft YaHei UI", 10)
        self.option_add("*Font", default_font)
        style.configure("TFrame", background="#FFFFFF")
        style.configure("Page.TFrame", background="#EEF3F6")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("TLabel", background="#FFFFFF", foreground="#21313C")
        style.configure("Muted.TLabel", foreground="#637581")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"), foreground="#123E52")
        style.configure("Subtitle.TLabel", foreground="#54717E")
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(15, 9))
        style.configure("TButton", padding=(11, 7))
        style.configure("Treeview", rowheight=30, font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"), padding=(5, 8))
        style.map("Treeview", background=[("selected", "#D5EAF2")], foreground=[("selected", "#123E52")])

    def _build_ui(self) -> None:
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self, style="Page.TFrame", padding=(22, 16, 22, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        title_box = ttk.Frame(header, style="Page.TFrame")
        title_box.grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text=APP_NAME, style="Title.TLabel", background="#EEF3F6").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            title_box,
            text="手机拍照 → 电脑批量识别 → 导出 Excel　｜　完全离线 · 支持常见图片格式",
            style="Subtitle.TLabel",
            background="#EEF3F6",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(
            header,
            text="照片只在本机处理，不上传、不改动原图",
            foreground="#167C69",
            background="#EEF3F6",
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        settings = ttk.Frame(self, style="Card.TFrame", padding=(18, 12))
        settings.grid(row=1, column=0, sticky="ew", padx=22)
        settings.grid_columnconfigure(7, weight=1)
        ttk.Label(settings, text="批次/箱号").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.batch_var, width=18).grid(row=0, column=1, padx=(7, 18))
        ttk.Label(settings, text="表号位数").grid(row=0, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.length_var, width=7).grid(row=0, column=3, padx=(7, 18))
        ttk.Label(settings, text="固定前缀").grid(row=0, column=4, sticky="w")
        ttk.Entry(settings, textvariable=self.prefix_var, width=12).grid(row=0, column=5, padx=(7, 18))
        ttk.Checkbutton(settings, text="仅纯数字", variable=self.digits_only_var).grid(row=0, column=6)
        ttk.Checkbutton(settings, text="扫描子文件夹", variable=self.recursive_var).grid(
            row=0, column=7, sticky="w", padx=(14, 0)
        )
        ttk.Label(settings, text="位数留空表示不限制", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=8, sticky="w", pady=(7, 0)
        )

        toolbar = ttk.Frame(self, style="Page.TFrame", padding=(22, 12, 22, 8))
        toolbar.grid(row=2, column=0, sticky="ew")
        toolbar.grid_columnconfigure(7, weight=1)
        ttk.Button(toolbar, text="选择照片文件夹", style="Primary.TButton", command=self._choose_folder).grid(
            row=0, column=0, padx=(0, 7)
        )
        ttk.Button(toolbar, text="添加照片", command=self._choose_files).grid(row=0, column=1, padx=7)
        self.scan_button = ttk.Button(toolbar, text="开始识别", style="Primary.TButton", command=self._start_scan)
        self.scan_button.grid(row=0, column=2, padx=7)
        self.cancel_button = ttk.Button(toolbar, text="取消", command=self._cancel_scan, state="disabled")
        self.cancel_button.grid(row=0, column=3, padx=7)
        ttk.Button(toolbar, text="清空", command=self._clear_all).grid(row=0, column=4, padx=7)
        self.filter_button = ttk.Checkbutton(
            toolbar,
            text="只看异常",
            variable=self.show_exceptions_only,
            command=self._refresh_table,
        )
        self.filter_button.grid(row=0, column=5, padx=(16, 7))
        self.export_button = ttk.Button(
            toolbar, text="导出 Excel / CSV", command=self._export_results, state="disabled"
        )
        self.export_button.grid(row=0, column=6, padx=7)
        ttk.Label(toolbar, textvariable=self.source_var, style="Muted.TLabel", background="#EEF3F6").grid(
            row=0, column=7, sticky="e"
        )

        status_bar = ttk.Frame(self, style="Page.TFrame", padding=(22, 0, 22, 10))
        status_bar.grid(row=3, column=0, sticky="ew")
        status_bar.grid_columnconfigure(0, weight=1)
        ttk.Progressbar(status_bar, variable=self.progress_var, maximum=100).grid(
            row=0, column=0, sticky="ew", padx=(0, 14)
        )
        ttk.Label(
            status_bar,
            textvariable=self.progress_text_var,
            background="#EEF3F6",
            foreground="#46616E",
            width=38,
        ).grid(row=0, column=1, sticky="e")

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.grid(row=4, column=0, sticky="nsew", padx=22, pady=(0, 12))
        table_card = ttk.Frame(body, style="Card.TFrame", padding=12)
        preview_card = ttk.Frame(body, style="Card.TFrame", padding=14, width=350)
        body.add(table_card, weight=4)
        body.add(preview_card, weight=1)
        self._build_table(table_card)
        self._build_preview(preview_card)

        footer = ttk.Frame(self, style="Page.TFrame", padding=(22, 0, 22, 14))
        footer.grid(row=5, column=0, sticky="ew")
        footer.grid_columnconfigure(5, weight=1)
        cards = [
            ("照片", "total", "#365E74"),
            ("自动通过", "auto", "#16866F"),
            ("待复核", "review", "#C57719"),
            ("未识别", "unread", "#B64B4B"),
            ("重复表号", "duplicate", "#7B55A5"),
        ]
        for index, (label, key, color) in enumerate(cards):
            card = tk.Frame(footer, bg="#FFFFFF", highlightthickness=1, highlightbackground="#DDE6EB")
            card.grid(row=0, column=index, sticky="w", padx=(0, 10))
            tk.Label(card, text=label, bg="#FFFFFF", fg="#637581", font=("Microsoft YaHei UI", 9)).grid(
                row=0, column=0, padx=(11, 5), pady=8
            )
            tk.Label(
                card,
                textvariable=self.summary_vars[key],
                bg="#FFFFFF",
                fg=color,
                font=("Microsoft YaHei UI", 12, "bold"),
            ).grid(row=0, column=1, padx=(0, 11), pady=8)

    def _build_table(self, parent: ttk.Frame) -> None:
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        ttk.Label(parent, text="识别结果", font=("Microsoft YaHei UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        table_box = ttk.Frame(parent)
        table_box.grid(row=1, column=0, sticky="nsew")
        table_box.grid_rowconfigure(0, weight=1)
        table_box.grid_columnconfigure(0, weight=1)
        columns = ("sequence", "status", "meter", "format", "file", "reason")
        self.tree = ttk.Treeview(table_box, columns=columns, show="headings", selectmode="browse")
        headings = {
            "sequence": "序号",
            "status": "状态",
            "meter": "表号",
            "format": "码制",
            "file": "照片文件名",
            "reason": "说明",
        }
        widths = {"sequence": 58, "status": 88, "meter": 165, "format": 85, "file": 220, "reason": 260}
        for name in columns:
            self.tree.heading(name, text=headings[name])
            anchor = "center" if name in {"sequence", "status", "meter", "format"} else "w"
            self.tree.column(name, width=widths[name], minwidth=50, anchor=anchor)
        self.tree.tag_configure("auto", foreground="#126D5C")
        self.tree.tag_configure("manual", foreground="#1E5E89")
        self.tree.tag_configure("review", foreground="#A35E09", background="#FFF9EB")
        self.tree.tag_configure("unread", foreground="#A83E3E", background="#FFF2F2")
        self.tree.tag_configure("duplicate", foreground="#75429B", background="#F8F0FF")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y = ttk.Scrollbar(table_box, orient=tk.VERTICAL, command=self.tree.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x = ttk.Scrollbar(table_box, orient=tk.HORIZONTAL, command=self.tree.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", lambda _event: self._manual_edit())

    def _build_preview(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        ttk.Label(parent, text="照片复核", font=("Microsoft YaHei UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.preview_label = tk.Label(
            parent,
            text="在左侧选择一条记录\n此处会显示原图和条码位置",
            bg="#F2F5F7",
            fg="#6A7D87",
            relief="flat",
            compound=tk.TOP,
            justify=tk.CENTER,
        )
        self.preview_label.grid(row=1, column=0, sticky="nsew")
        self.preview_details = tk.StringVar(value="")
        ttk.Label(
            parent,
            textvariable=self.preview_details,
            wraplength=320,
            justify=tk.LEFT,
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="ew", pady=(10, 8))
        actions = ttk.Frame(parent)
        actions.grid(row=3, column=0, sticky="ew")
        for column in range(3):
            actions.grid_columnconfigure(column, weight=1)
        ttk.Button(actions, text="确认/修改表号", command=self._manual_edit).grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=(0, 5)
        )
        ttk.Button(actions, text="重新识别", command=self._rescan_selected).grid(
            row=0, column=2, sticky="ew", padx=(5, 0)
        )
        ttk.Button(actions, text="打开原图", command=self._open_selected).grid(
            row=1, column=0, sticky="ew", padx=(0, 5), pady=(8, 0)
        )
        ttk.Button(actions, text="上一条", command=lambda: self._select_relative(-1)).grid(
            row=1, column=1, sticky="ew", padx=5, pady=(8, 0)
        )
        ttk.Button(actions, text="下一条异常", command=self._select_next_exception).grid(
            row=1, column=2, sticky="ew", padx=(5, 0), pady=(8, 0)
        )

    def _settings(self) -> ScanSettings | None:
        try:
            exact_length = parse_exact_length(self.length_var.get())
        except ValueError as exc:
            messagebox.showerror("设置有误", str(exc), parent=self)
            return None
        return ScanSettings(
            exact_length=exact_length,
            digits_only=self.digits_only_var.get(),
            prefix=self.prefix_var.get().strip(),
        )

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择存放水表照片的文件夹", parent=self)
        if not folder:
            return
        paths = discover_images(Path(folder), recursive=self.recursive_var.get())
        if not paths:
            messagebox.showwarning("没有照片", "所选文件夹中没有支持的图片。", parent=self)
            return
        self.files = paths
        self.source_var.set(f"已选择 {len(paths)} 张照片：{folder}")
        self.progress_text_var.set(f"已就绪，共 {len(paths)} 张；点击“开始识别”")
        self.summary_vars["total"].set(str(len(paths)))

    def _choose_files(self) -> None:
        patterns = " ".join(f"*{suffix}" for suffix in sorted(SUPPORTED_EXTENSIONS))
        selected = filedialog.askopenfilenames(
            title="添加水表照片",
            filetypes=[("支持的图片", patterns), ("所有文件", "*.*")],
            parent=self,
        )
        if not selected:
            return
        unique: dict[str, Path] = {str(path).casefold(): path for path in self.files}
        for value in selected:
            path = Path(value)
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                unique[str(path).casefold()] = path
        self.files = sorted(unique.values(), key=lambda path: str(path).casefold())
        self.source_var.set(f"已添加 {len(self.files)} 张照片")
        self.progress_text_var.set(f"已就绪，共 {len(self.files)} 张；点击“开始识别”")
        self.summary_vars["total"].set(str(len(self.files)))

    def _start_scan(self) -> None:
        if self.scan_thread and self.scan_thread.is_alive():
            return
        if not self.files:
            messagebox.showinfo("请先选择照片", "请先选择照片文件夹或添加照片。", parent=self)
            return
        settings = self._settings()
        if settings is None:
            return

        self.records.clear()
        self._refresh_table()
        self.cancel_event.clear()
        self.progress_var.set(0)
        self.progress_text_var.set("正在准备识别……")
        self.scan_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.export_button.configure(state="disabled")
        self.scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(list(self.files), settings),
            name="barcode-scan-worker",
            daemon=True,
        )
        self.scan_thread.start()

    def _scan_worker(self, paths: list[Path], settings: ScanSettings) -> None:
        total = len(paths)
        for index, path in enumerate(paths, start=1):
            if self.cancel_event.is_set():
                self.scan_queue.put(("finished", True))
                return
            result = scan_image(path, settings, sequence=index)
            self.scan_queue.put(("result", result, index, total))
        self.scan_queue.put(("finished", False))

    def _poll_queue(self) -> None:
        try:
            while True:
                event = self.scan_queue.get_nowait()
                if event[0] == "result":
                    _, record, index, total = event
                    self.records.append(record)
                    self.progress_var.set(index / total * 100)
                    self.progress_text_var.set(f"正在识别 {index}/{total}：{record.file_name}")
                    self._insert_record(record)
                    self._update_summary()
                elif event[0] == "rescan":
                    _, sequence, replacement = event
                    self._finish_rescan(sequence, replacement)
                elif event[0] == "finished":
                    _, cancelled = event
                    self._finish_scan(cancelled)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _finish_scan(self, cancelled: bool) -> None:
        mark_duplicates(self.records)
        self._refresh_table()
        self._update_summary()
        self.scan_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.export_button.configure(state="normal" if self.records else "disabled")
        if cancelled:
            self.progress_text_var.set(f"已取消；保留前 {len(self.records)} 条结果")
        else:
            self.progress_var.set(100)
            review_count = sum(record.is_exception for record in self.records)
            self.progress_text_var.set(
                f"识别完成：{len(self.records)} 张，{review_count} 条需要复核"
                if review_count
                else f"识别完成：{len(self.records)} 张，全部通过"
            )

    def _cancel_scan(self) -> None:
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.progress_text_var.set("正在取消，请稍候……")

    def _clear_all(self) -> None:
        if self.scan_thread and self.scan_thread.is_alive():
            messagebox.showinfo("正在识别", "请先取消当前识别任务。", parent=self)
            return
        if (self.files or self.records) and not messagebox.askyesno(
            "确认清空", "清空当前照片列表和识别结果？原图不会被删除。", parent=self
        ):
            return
        self.files.clear()
        self.records.clear()
        self.progress_var.set(0)
        self.source_var.set("尚未选择照片")
        self.progress_text_var.set("请选择照片文件夹或若干照片")
        self.preview_label.configure(image="", text="在左侧选择一条记录\n此处会显示原图和条码位置")
        self.preview_photo = None
        self.preview_details.set("")
        self.export_button.configure(state="disabled")
        self._refresh_table()
        self._update_summary()

    def _record_tag(self, record: ScanRecord) -> str:
        if record.duplicate:
            return "duplicate"
        return {
            STATUS_AUTO: "auto",
            STATUS_MANUAL: "manual",
            STATUS_REVIEW: "review",
            STATUS_UNREAD: "unread",
        }.get(record.status, "")

    def _insert_record(self, record: ScanRecord) -> None:
        if self.show_exceptions_only.get() and not record.is_exception:
            return
        display_reason = record.reason
        if record.duplicate:
            display_reason = (display_reason + "；" if display_reason else "") + "重复表号"
        self.tree.insert(
            "",
            tk.END,
            iid=f"record-{record.sequence}",
            values=(
                record.sequence,
                record.status,
                record.meter_no or "—",
                record.barcode_formats or "—",
                record.file_name,
                display_reason,
            ),
            tags=(self._record_tag(record),),
        )

    def _refresh_table(self) -> None:
        selected = self.tree.selection()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for record in self.records:
            self._insert_record(record)
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])

    def _update_summary(self) -> None:
        source_total = len(self.files) if self.files else len(self.records)
        self.summary_vars["total"].set(str(source_total))
        self.summary_vars["auto"].set(str(sum(record.status == STATUS_AUTO for record in self.records)))
        self.summary_vars["review"].set(str(sum(record.status == STATUS_REVIEW for record in self.records)))
        self.summary_vars["unread"].set(str(sum(record.status == STATUS_UNREAD for record in self.records)))
        self.summary_vars["duplicate"].set(str(sum(record.duplicate for record in self.records)))

    def _selected_record(self) -> ScanRecord | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            sequence = int(selection[0].split("-", 1)[1])
        except (IndexError, ValueError):
            return None
        return next((record for record in self.records if record.sequence == sequence), None)

    def _on_tree_select(self, _event: object = None) -> None:
        record = self._selected_record()
        if record is None:
            return
        self._show_preview(record)

    def _show_preview(self, record: ScanRecord) -> None:
        try:
            with Image.open(record.source_path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
            candidate = next((item for item in record.candidates if item.text == record.meter_no), None)
            candidate = candidate or (record.candidates[0] if record.candidates else None)
            if candidate and candidate.position:
                draw = ImageDraw.Draw(image)
                width = max(5, round(max(image.size) / 350))
                draw.line(list(candidate.position) + [candidate.position[0]], fill="#F04444", width=width)
            image.thumbnail((340, 455), Image.Resampling.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self.preview_photo, text="")
        except Exception as exc:
            self.preview_photo = None
            self.preview_label.configure(image="", text=f"无法显示预览\n{type(exc).__name__}")

        details = [
            f"文件：{record.file_name}",
            f"状态：{record.status}" + ("（重复表号）" if record.duplicate else ""),
            f"表号：{record.meter_no or '尚未确认'}",
        ]
        if record.raw_values:
            details.append(f"原始识别：{record.raw_values}")
        if record.reason:
            details.append(f"说明：{record.reason}")
        self.preview_details.set("\n".join(details))

    def _manual_edit(self) -> None:
        record = self._selected_record()
        if record is None:
            messagebox.showinfo("请选择记录", "请先在左侧选择一张照片。", parent=self)
            return
        settings = self._settings()
        if settings is None:
            return
        initial = record.meter_no or (record.candidates[0].text if record.candidates else "")
        candidates = "、".join(candidate.text for candidate in record.candidates)
        prompt = "请输入并核对表号："
        if len(record.candidates) > 1:
            prompt += f"\n检测到的候选：{candidates}"
        value = simpledialog.askstring("确认/修改表号", prompt, initialvalue=initial, parent=self)
        if value is None:
            return
        value = value.strip()
        if not value:
            messagebox.showwarning("表号不能为空", "请输入确认后的表号。", parent=self)
            return
        validation_error = settings.validation_error(value)
        if validation_error and not messagebox.askyesno(
            "不符合当前规则",
            f"该表号{validation_error}。仍要人工确认并保存吗？",
            parent=self,
        ):
            return
        apply_manual_value(record, value, settings)
        mark_duplicates(self.records)
        self._refresh_table()
        self._update_summary()
        iid = f"record-{record.sequence}"
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)
        self._show_preview(record)

    def _rescan_selected(self) -> None:
        if self.scan_thread and self.scan_thread.is_alive():
            messagebox.showinfo("正在识别", "请等待当前批量识别结束后再重试。", parent=self)
            return
        record = self._selected_record()
        if record is None:
            messagebox.showinfo("请选择记录", "请先在左侧选择一张照片。", parent=self)
            return
        settings = self._settings()
        if settings is None:
            return
        self.progress_text_var.set(f"正在重新识别：{record.file_name}")
        self.scan_thread = threading.Thread(
            target=lambda: self.scan_queue.put(
                ("rescan", record.sequence, scan_image(record.source_path, settings, record.sequence))
            ),
            daemon=True,
        )
        self.scan_thread.start()

    def _finish_rescan(self, sequence: int, replacement: ScanRecord) -> None:
        for index, record in enumerate(self.records):
            if record.sequence == sequence:
                self.records[index] = replacement
                break
        mark_duplicates(self.records)
        self._refresh_table()
        self._update_summary()
        iid = f"record-{sequence}"
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self._show_preview(replacement)
        self.progress_text_var.set(f"重新识别完成：{replacement.status}")

    def _open_selected(self) -> None:
        record = self._selected_record()
        if record is None:
            messagebox.showinfo("请选择记录", "请先在左侧选择一张照片。", parent=self)
            return
        try:
            os.startfile(record.source_path)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc), parent=self)

    def _select_relative(self, offset: int) -> None:
        children = self.tree.get_children()
        if not children:
            return
        selection = self.tree.selection()
        index = children.index(selection[0]) if selection and selection[0] in children else 0
        target = children[max(0, min(len(children) - 1, index + offset))]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self._on_tree_select()

    def _select_next_exception(self) -> None:
        if not self.records:
            return
        selected = self._selected_record()
        start = self.records.index(selected) + 1 if selected in self.records else 0
        ordered = self.records[start:] + self.records[:start]
        target_record = next((record for record in ordered if record.is_exception), None)
        if target_record is None:
            messagebox.showinfo("没有异常", "当前没有需要复核的记录。", parent=self)
            return
        if self.show_exceptions_only.get() is False and not self.tree.exists(f"record-{target_record.sequence}"):
            self._refresh_table()
        iid = f"record-{target_record.sequence}"
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self._show_preview(target_record)

    def _export_results(self) -> None:
        if not self.records:
            messagebox.showinfo("没有结果", "请先完成识别。", parent=self)
            return
        exception_count = sum(record.is_exception for record in self.records)
        if exception_count and not messagebox.askyesno(
            "仍有待复核项",
            f"还有 {exception_count} 条待复核、未识别或重复记录。\n可以继续导出，异常项会单列保存。是否继续？",
            parent=self,
        ):
            return
        batch = self.batch_var.get().strip()
        safe_batch = "".join(character for character in batch if character not in '<>:"/\\|?*').strip()
        default_name = f"水表表号_{safe_batch + '_' if safe_batch else ''}{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        target_value = filedialog.asksaveasfilename(
            title="导出识别结果",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel 工作簿", "*.xlsx"), ("CSV 表格", "*.csv")],
            parent=self,
        )
        if not target_value:
            return
        target = Path(target_value)
        try:
            if target.suffix.lower() == ".csv":
                export_csv(self.records, target, batch)
            else:
                if target.suffix.lower() != ".xlsx":
                    target = target.with_suffix(".xlsx")
                export_xlsx(self.records, target, batch)
        except PermissionError:
            messagebox.showerror("导出失败", "文件可能正在 Excel 中打开，请关闭后重试。", parent=self)
            return
        except Exception as exc:
            messagebox.showerror("导出失败", f"{type(exc).__name__}: {exc}", parent=self)
            return
        messagebox.showinfo("导出完成", f"结果已保存到：\n{target}", parent=self)

    def _on_close(self) -> None:
        if self.scan_thread and self.scan_thread.is_alive():
            if not messagebox.askyesno("仍在识别", "识别尚未结束，确定退出吗？", parent=self):
                return
            self.cancel_event.set()
        self.destroy()


def run_self_test(image_path: str, exact_length: int | None) -> int:
    result = scan_image(Path(image_path), ScanSettings(exact_length=exact_length), sequence=1)
    print(
        json.dumps(
            {
                "file": str(result.source_path),
                "status": result.status,
                "meter_no": result.meter_no,
                "raw_values": result.raw_values,
                "formats": result.barcode_formats,
                "reason": result.reason,
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.meter_no else 2


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--self-test", metavar="IMAGE", help="识别一张图片并输出 JSON，不启动 GUI")
    parser.add_argument("--length", type=int, default=14, help="自检时期望的表号位数")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test(args.self_test, args.length)
    app = MeterReaderApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
