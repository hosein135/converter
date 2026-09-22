from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from av2converter import library
from av2converter.convert import ConvertError, ConvertSettings, convert_file
from av2converter.paths import converted_dir
from av2converter.player import PlayerError, open_in_vlc_av2, reveal_in_file_manager, vlc_av2_binary

VIDEO_TYPES = [
    (
        "Video files",
        "*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.ts *.m2ts *.wmv *.flv *.ogv *.mpeg *.mpg",
    ),
    ("All files", "*.*"),
]


class ConverterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AV2 Converter")
        self.geometry("920x620")
        self.minsize(760, 520)
        self._busy = False
        self._source = tk.StringVar()
        self._output = tk.StringVar()
        self._cpu = tk.IntVar(value=9)
        self._cq = tk.IntVar(value=32)
        self._audio_mode = tk.StringVar(value="5")
        self._status = tk.StringVar(value="Ready")
        self._configure_style()
        self._build()
        self.refresh_library()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self) -> None:
        self.configure(bg="#12141a")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        bg = "#12141a"
        panel = "#1b1e27"
        fg = "#e8eaed"
        muted = "#9aa0a6"
        accent = "#7c5cff"
        style.configure(".", background=bg, foreground=fg, fieldbackground=panel)
        style.configure("TFrame", background=bg)
        style.configure("Card.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("Muted.TLabel", background=bg, foreground=muted)
        style.configure("Card.TLabel", background=panel, foreground=fg)
        style.configure("Header.TLabel", background=bg, foreground=fg, font=("Segoe UI", 18, "bold"))
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), background="#252833", foreground=fg)
        style.map("TNotebook.Tab", background=[("selected", accent)])
        style.configure("TButton", padding=(12, 6), background="#2a2e3a", foreground=fg)
        style.map("TButton", background=[("active", accent)])
        style.configure("Accent.TButton", background=accent, foreground="#fff")
        style.configure("TEntry", fieldbackground=panel, foreground=fg)
        style.configure("TSpinbox", fieldbackground=panel, foreground=fg)
        style.configure("TCombobox", fieldbackground=panel, foreground=fg)
        style.configure("TProgressbar", background=accent, troughcolor="#252833")
        style.configure(
            "Treeview",
            background=panel,
            foreground=fg,
            fieldbackground=panel,
            rowheight=28,
            borderwidth=0,
        )
        style.configure("Treeview.Heading", background="#252833", foreground=fg, relief="flat")
        style.map("Treeview", background=[("selected", accent)])

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="AV2 Converter", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Video → AV2 (AVM)    Audio → xHE-AAC (exhale)    Play with vlc-av2",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        convert = ttk.Frame(self.notebook, padding=12)
        converted = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(convert, text="Convert")
        self.notebook.add(converted, text="Converted")
        self._build_convert(convert)
        self._build_converted(converted)

        status = ttk.Frame(outer)
        status.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(status, textvariable=self._status, style="Muted.TLabel").pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=180)
        self.progress.pack(side=tk.RIGHT)

    def _build_convert(self, parent: ttk.Frame) -> None:
        grid = ttk.Frame(parent)
        grid.pack(fill=tk.X)
        grid.columnconfigure(1, weight=1)

        ttk.Label(grid, text="Source").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self._source).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(grid, text="Browse…", command=self._browse_source).grid(row=0, column=2)

        ttk.Label(grid, text="Output").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self._output).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(grid, text="Browse…", command=self._browse_output).grid(row=1, column=2)

        opts = ttk.Frame(parent)
        opts.pack(fill=tk.X, pady=16)
        self._labeled_spin(opts, "Speed (cpu-used, higher = faster)", self._cpu, 0, 9, 0)
        self._labeled_spin(opts, "Quality (cq-level, lower = better)", self._cq, 10, 55, 1)

        audio_row = ttk.Frame(opts)
        audio_row.grid(row=0, column=2, padx=16, sticky="w")
        ttk.Label(audio_row, text="xHE-AAC mode").pack(anchor="w")
        modes = list("0123456789") + list("abcdefg")
        ttk.Combobox(
            audio_row,
            textvariable=self._audio_mode,
            values=modes,
            width=8,
            state="readonly",
        ).pack(anchor="w", pady=(4, 0))

        ttk.Label(
            parent,
            text="Resolution, frame rate, and bit depth stay as in the source. "
            "Only the video codec becomes AV2 and the audio codec becomes xHE-AAC. "
            "AVM uses every CPU and a faster search so a short clip can finish. "
            "Playback uses vlc-av2 (https://github.com/afen261/vlc-av2).",
            style="Muted.TLabel",
            wraplength=820,
        ).pack(anchor="w")

        btns = ttk.Frame(parent)
        btns.pack(fill=tk.X, pady=12)
        self.convert_btn = ttk.Button(
            btns, text="Convert to AV2 + xHE-AAC", style="Accent.TButton", command=self._start_convert
        )
        self.convert_btn.pack(side=tk.LEFT)

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(
            log_frame,
            height=12,
            bg="#0e1016",
            fg="#d0d4dc",
            insertbackground="#e8eaed",
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
        )
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _labeled_spin(self, parent: ttk.Frame, label: str, var: tk.IntVar, lo: int, hi: int, col: int) -> None:
        box = ttk.Frame(parent)
        box.grid(row=0, column=col, rowspan=2, padx=(0, 16), sticky="w")
        ttk.Label(box, text=label).pack(anchor="w")
        ttk.Spinbox(box, from_=lo, to=hi, textvariable=var, width=8).pack(anchor="w", pady=(4, 0))

    def _build_converted(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Double-click a file to open it in vlc-av2.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        columns = ("name", "codecs", "size", "created")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="File")
        self.tree.heading("codecs", text="Codecs")
        self.tree.heading("size", text="Size")
        self.tree.heading("created", text="Converted")
        self.tree.column("name", width=360)
        self.tree.column("codecs", width=160)
        self.tree.column("size", width=100)
        self.tree.column("created", width=180)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self._play_selected)
        self.tree.bind("<Return>", self._play_selected)

        menu = tk.Menu(self, tearoff=0, bg="#1b1e27", fg="#e8eaed")
        menu.add_command(label="Play in vlc-av2", command=self._play_selected)
        menu.add_command(label="Show in folder", command=self._reveal_selected)
        menu.add_separator()
        menu.add_command(label="Remove from list", command=self._remove_selected)
        menu.add_command(label="Delete file", command=self._delete_selected)
        self.tree.bind("<Button-3>", lambda e: self._popup(menu, e))

        btns = ttk.Frame(parent)
        btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btns, text="Play", command=self._play_selected).pack(side=tk.LEFT)
        ttk.Button(btns, text="Refresh", command=self.refresh_library).pack(side=tk.LEFT, padx=8)

    def _popup(self, menu: tk.Menu, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        menu.tk_popup(event.x_root, event.y_root)

    def _browse_source(self) -> None:
        path = filedialog.askopenfilename(title="Choose a video", filetypes=VIDEO_TYPES)
        if not path:
            return
        self._source.set(path)
        dest = converted_dir() / f"{Path(path).stem}.av2.mp4"
        self._output.set(str(dest))

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save converted video",
            defaultextension=".mp4",
            filetypes=[("MP4", "*.mp4"), ("All files", "*.*")],
            initialfile=Path(self._output.get() or "output.av2.mp4").name,
        )
        if path:
            self._output.set(path)

    def _append_log(self, line: str) -> None:
        self.log.insert(tk.END, line + "\n")
        self.log.see(tk.END)

    def _start_convert(self) -> None:
        if self._busy:
            return
        source = self._source.get().strip()
        if not source:
            messagebox.showinfo("AV2 Converter", "Choose a source video first.")
            return
        output = self._output.get().strip() or None
        settings = ConvertSettings(
            cpu_used=int(self._cpu.get()),
            cq_level=int(self._cq.get()),
            audio_mode=str(self._audio_mode.get()),
        )
        self._busy = True
        self.convert_btn.state(["disabled"])
        self.progress.start(12)
        self._status.set("Converting…")
        self.log.delete("1.0", tk.END)

        def work() -> None:
            try:
                dest = convert_file(
                    source,
                    output=output,
                    settings=settings,
                    log=lambda line: self.after(0, self._append_log, line),
                )
            except (ConvertError, OSError) as exc:
                self.after(0, self._convert_failed, str(exc))
                return
            self.after(0, self._convert_done, str(dest))

        threading.Thread(target=work, daemon=True).start()

    def _convert_done(self, dest: str) -> None:
        self._busy = False
        self.convert_btn.state(["!disabled"])
        self.progress.stop()
        self._status.set(f"Finished: {dest}")
        self.refresh_library()
        self.notebook.select(1)
        messagebox.showinfo("AV2 Converter", f"Converted:\n{dest}\n\nDouble-click it in Converted to play in vlc-av2.")

    def _convert_failed(self, error: str) -> None:
        self._busy = False
        self.convert_btn.state(["!disabled"])
        self.progress.stop()
        self._status.set("Conversion failed")
        self._append_log(error)
        messagebox.showerror("Conversion failed", error)

    def refresh_library(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in library.items():
            path = Path(item.get("output") or "")
            size = item.get("size") or (path.stat().st_size if path.is_file() else 0)
            codecs = f"{item.get('video_codec', 'AV2')} + {item.get('audio_codec', 'xHE-AAC')}"
            self.tree.insert(
                "",
                tk.END,
                iid=item.get("id"),
                values=(
                    path.name,
                    codecs,
                    _fmt_size(size),
                    item.get("created", ""),
                ),
            )

    def _selected_item(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        item_id = sel[0]
        for item in library.items():
            if item.get("id") == item_id:
                return item
        return None

    def _play_selected(self, _event: object | None = None) -> None:
        item = self._selected_item()
        if not item:
            return
        path = item.get("output")
        try:
            vlc_av2_binary()
            open_in_vlc_av2(path)
            self._status.set(f"Playing in vlc-av2: {path}")
        except PlayerError as exc:
            messagebox.showerror("vlc-av2", str(exc))

    def _reveal_selected(self) -> None:
        item = self._selected_item()
        if item:
            reveal_in_file_manager(item.get("output"))

    def _remove_selected(self) -> None:
        item = self._selected_item()
        if not item:
            return
        library.remove_item(item["id"], delete_file=False)
        self.refresh_library()

    def _delete_selected(self) -> None:
        item = self._selected_item()
        if not item:
            return
        if not messagebox.askyesno("Delete", f"Delete {item.get('output')}?"):
            return
        library.remove_item(item["id"], delete_file=True)
        self.refresh_library()

    def _on_close(self) -> None:
        if self._busy and not messagebox.askyesno(
            "Quit",
            "A conversion is still running. Quit anyway?",
        ):
            return
        self.destroy()


def _fmt_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def run_gui(_argv: list[str] | None = None) -> int:
    if not os.environ.get("DISPLAY") and os.name != "nt" and not os.environ.get("WAYLAND_DISPLAY"):
        print("No DISPLAY/WAYLAND_DISPLAY — cannot open the GUI.", flush=True)
        print("On a Linux VM, run a desktop session (or X11/Wayland forwarding), then re-run ./run.sh", flush=True)
        return 1
    app = ConverterApp()
    app.mainloop()
    return 0
