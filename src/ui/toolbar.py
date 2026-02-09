"""Toolbar component with recording and replay controls."""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional


class Toolbar(ttk.Frame):
    """Top toolbar with Start/Stop/Pause recording, Replay, and Settings buttons."""

    ALL_MACROS_LABEL = "(All Macros)"

    def __init__(
        self,
        parent,
        on_start: Optional[Callable] = None,
        on_stop: Optional[Callable] = None,
        on_pause: Optional[Callable] = None,
        on_replay: Optional[Callable] = None,
        on_stop_replay: Optional[Callable] = None,
        on_settings: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_pause = on_pause
        self.on_replay = on_replay
        self.on_stop_replay = on_stop_replay
        self.on_settings = on_settings
        self._build_ui()

    def _build_ui(self):
        self.configure(padding=(5, 5))

        # Recording controls
        rec_label = ttk.Label(self, text="Recording:", font=("Segoe UI", 9))
        rec_label.pack(side=tk.LEFT, padx=(5, 5))

        self.start_btn = ttk.Button(
            self, text="Start", command=self._on_start, width=8
        )
        self.start_btn.pack(side=tk.LEFT, padx=2)

        self.stop_btn = ttk.Button(
            self, text="Stop", command=self._on_stop, width=8, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=2)

        self.pause_btn = ttk.Button(
            self, text="Pause", command=self._on_pause, width=8, state=tk.DISABLED
        )
        self.pause_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(self, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10, pady=2
        )

        # Replay controls
        replay_label = ttk.Label(self, text="Replay:", font=("Segoe UI", 9))
        replay_label.pack(side=tk.LEFT, padx=(5, 5))

        # Macro selector dropdown
        self._macro_var = tk.StringVar(value=self.ALL_MACROS_LABEL)
        self.macro_selector = ttk.Combobox(
            self,
            textvariable=self._macro_var,
            values=[self.ALL_MACROS_LABEL],
            state="readonly",
            width=22,
        )
        self.macro_selector.pack(side=tk.LEFT, padx=2)

        self.replay_btn = ttk.Button(
            self, text="Replay", command=self._on_replay, width=8
        )
        self.replay_btn.pack(side=tk.LEFT, padx=2)

        self.stop_replay_btn = ttk.Button(
            self, text="Stop", command=self._on_stop_replay, width=8, state=tk.DISABLED
        )
        self.stop_replay_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(self, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10, pady=2
        )

        # Settings
        self.settings_btn = ttk.Button(
            self, text="Settings", command=self._on_settings, width=8
        )
        self.settings_btn.pack(side=tk.LEFT, padx=2)

    def get_selected_macro(self) -> str:
        """Return the selected macro name, or empty string for 'all'."""
        val = self._macro_var.get()
        if val == self.ALL_MACROS_LABEL:
            return ""
        return val

    def update_macro_list(self, macro_names: List[str]):
        """Update the macro selector dropdown with available macro names."""
        values = [self.ALL_MACROS_LABEL] + macro_names
        self.macro_selector["values"] = values
        # Keep current selection if still valid
        current = self._macro_var.get()
        if current not in values:
            self._macro_var.set(self.ALL_MACROS_LABEL)

    def set_recording_state(self, is_recording: bool, is_paused: bool = False):
        """Update button states based on recording state."""
        if is_recording:
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.NORMAL)
            self.replay_btn.config(state=tk.DISABLED)
            self.macro_selector.config(state=tk.DISABLED)
            if is_paused:
                self.pause_btn.config(text="Resume")
            else:
                self.pause_btn.config(text="Pause")
        else:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.DISABLED, text="Pause")
            self.replay_btn.config(state=tk.NORMAL)
            self.macro_selector.config(state="readonly")

    def set_replay_state(self, is_running: bool):
        """Update button states for replay."""
        if is_running:
            self.replay_btn.config(state=tk.DISABLED)
            self.stop_replay_btn.config(state=tk.NORMAL)
            self.start_btn.config(state=tk.DISABLED)
            self.macro_selector.config(state=tk.DISABLED)
        else:
            self.replay_btn.config(state=tk.NORMAL)
            self.stop_replay_btn.config(state=tk.DISABLED)
            self.start_btn.config(state=tk.NORMAL)
            self.macro_selector.config(state="readonly")

    def _on_start(self):
        if self.on_start:
            self.on_start()

    def _on_stop(self):
        if self.on_stop:
            self.on_stop()

    def _on_pause(self):
        if self.on_pause:
            self.on_pause()

    def _on_replay(self):
        if self.on_replay:
            self.on_replay()

    def _on_stop_replay(self):
        if self.on_stop_replay:
            self.on_stop_replay()

    def _on_settings(self):
        if self.on_settings:
            self.on_settings()
