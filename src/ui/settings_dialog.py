"""Settings dialog for configuring the AHK Macro Builder."""

import tkinter as tk
from tkinter import ttk, filedialog

from src.settings import AppSettings


class SettingsDialog(tk.Toplevel):
    """Modal settings dialog."""

    def __init__(self, parent, settings: AppSettings, on_save=None):
        super().__init__(parent)
        self.title("Settings")
        self.settings = settings
        self.on_save = on_save
        self.result = None

        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        self._build_ui()
        self._load_values()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Recording Tab ---
        rec_frame = ttk.Frame(notebook, padding=15)
        notebook.add(rec_frame, text="Recording")

        row = 0
        ttk.Label(rec_frame, text="Coordinate Mode:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        self._coord_mode_var = tk.StringVar()
        coord_combo = ttk.Combobox(
            rec_frame,
            textvariable=self._coord_mode_var,
            values=["Screen", "Window", "Client"],
            state="readonly",
            width=15,
        )
        coord_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        row += 1
        self._record_moves_var = tk.BooleanVar()
        ttk.Checkbutton(
            rec_frame,
            text="Record mouse movements",
            variable=self._record_moves_var,
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)

        row += 1
        ttk.Label(rec_frame, text="Move sample rate (ms):").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        self._move_sample_var = tk.IntVar()
        ttk.Spinbox(
            rec_frame,
            textvariable=self._move_sample_var,
            from_=10,
            to=1000,
            increment=10,
            width=8,
        ).grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        row += 1
        ttk.Label(rec_frame, text="Drag threshold (pixels):").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        self._drag_threshold_var = tk.IntVar()
        ttk.Spinbox(
            rec_frame,
            textvariable=self._drag_threshold_var,
            from_=1,
            to=100,
            increment=1,
            width=8,
        ).grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        row += 1
        ttk.Label(rec_frame, text="Macro naming:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        self._naming_var = tk.StringVar()
        naming_combo = ttk.Combobox(
            rec_frame,
            textvariable=self._naming_var,
            values=["timestamp", "incremental"],
            state="readonly",
            width=15,
        )
        naming_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        row += 1
        ttk.Label(rec_frame, text="Macro prefix:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        self._prefix_var = tk.StringVar()
        ttk.Entry(rec_frame, textvariable=self._prefix_var, width=18).grid(
            row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0)
        )

        # --- Replay Tab ---
        replay_frame = ttk.Frame(notebook, padding=15)
        notebook.add(replay_frame, text="Replay")

        row = 0
        ttk.Label(replay_frame, text="AutoHotkey.exe path:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        ahk_frame = ttk.Frame(replay_frame)
        ahk_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self._ahk_path_var = tk.StringVar()
        ttk.Entry(ahk_frame, textvariable=self._ahk_path_var, width=30).pack(
            side=tk.LEFT
        )
        ttk.Button(ahk_frame, text="Browse", command=self._browse_ahk, width=7).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        row += 1
        ttk.Label(replay_frame, text="Speed multiplier:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        self._speed_var = tk.DoubleVar()
        ttk.Spinbox(
            replay_frame,
            textvariable=self._speed_var,
            from_=0.1,
            to=10.0,
            increment=0.1,
            width=8,
            format="%.1f",
        ).grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        row += 1
        ttk.Label(
            replay_frame,
            text="(1.0 = real time, 0.5 = half speed, 2.0 = double speed)",
            foreground="gray",
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        # --- Buttons ---
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(btn_frame, text="Cancel", command=self.destroy, width=10).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(btn_frame, text="Save", command=self._on_save, width=10).pack(
            side=tk.RIGHT, padx=5
        )

    def _load_values(self):
        """Populate UI fields from current settings."""
        self._coord_mode_var.set(self.settings.coord_mode)
        self._record_moves_var.set(self.settings.record_mouse_moves)
        self._move_sample_var.set(self.settings.mouse_move_sample_ms)
        self._drag_threshold_var.set(self.settings.drag_threshold_px)
        self._naming_var.set(self.settings.macro_naming)
        self._prefix_var.set(self.settings.macro_prefix)
        self._ahk_path_var.set(self.settings.ahk_exe_path)
        self._speed_var.set(self.settings.replay_speed_multiplier)

    def _browse_ahk(self):
        path = filedialog.askopenfilename(
            filetypes=[("Executables", "*.exe"), ("All Files", "*.*")],
            title="Select AutoHotkey.exe",
        )
        if path:
            self._ahk_path_var.set(path)

    def _on_save(self):
        """Apply settings and close."""
        self.settings.coord_mode = self._coord_mode_var.get()
        self.settings.record_mouse_moves = self._record_moves_var.get()
        self.settings.mouse_move_sample_ms = self._move_sample_var.get()
        self.settings.drag_threshold_px = self._drag_threshold_var.get()
        self.settings.macro_naming = self._naming_var.get()
        self.settings.macro_prefix = self._prefix_var.get()
        self.settings.ahk_exe_path = self._ahk_path_var.get()
        self.settings.replay_speed_multiplier = self._speed_var.get()

        self.result = self.settings
        if self.on_save:
            self.on_save(self.settings)
        self.destroy()
