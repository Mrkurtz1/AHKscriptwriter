"""Status bar component for the main window."""

import tkinter as tk
from tkinter import ttk

from src.models import RecordingState


class StatusBar(ttk.Frame):
    """Bottom status bar showing recording state, coordinates, and replay status."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.configure(relief=tk.SUNKEN, borderwidth=1)

        # Recording state indicator
        self._state_frame = ttk.Frame(self)
        self._state_frame.pack(side=tk.LEFT, padx=5, pady=2)

        self._recording_dot = tk.Canvas(
            self._state_frame, width=12, height=12, highlightthickness=0
        )
        self._recording_dot.pack(side=tk.LEFT, padx=(0, 4))
        self._dot_id = self._recording_dot.create_oval(2, 2, 10, 10, fill="gray")

        self._state_label = ttk.Label(self._state_frame, text="Idle", width=12)
        self._state_label.pack(side=tk.LEFT)

        ttk.Separator(self, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2
        )

        # Coordinate mode
        self._coord_label = ttk.Label(self, text="Mode: Screen", width=16)
        self._coord_label.pack(side=tk.LEFT, padx=5, pady=2)

        ttk.Separator(self, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2
        )

        # Last captured info
        self._capture_label = ttk.Label(self, text="Last: --", width=35)
        self._capture_label.pack(side=tk.LEFT, padx=5, pady=2)

        ttk.Separator(self, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2
        )

        # Replay status
        self._replay_label = ttk.Label(self, text="Replay: Idle", width=25)
        self._replay_label.pack(side=tk.LEFT, padx=5, pady=2)

        # Timer (right-aligned)
        self._timer_label = ttk.Label(self, text="", width=10, anchor=tk.E)
        self._timer_label.pack(side=tk.RIGHT, padx=5, pady=2)

    def set_recording_state(self, state: RecordingState):
        """Update the recording state indicator."""
        colors = {
            RecordingState.IDLE: "gray",
            RecordingState.RECORDING: "#e74c3c",
            RecordingState.PAUSED: "#f39c12",
        }
        self._recording_dot.itemconfig(self._dot_id, fill=colors.get(state, "gray"))
        self._state_label.config(text=state.value)

    def set_coord_mode(self, mode: str):
        """Update the coordinate mode display."""
        self._coord_label.config(text=f"Mode: {mode}")

    def set_last_capture(self, x: int, y: int, color: str):
        """Update the last captured coordinate and color."""
        self._capture_label.config(text=f"Last: ({x}, {y}) {color}")

    def set_replay_status(self, status: str):
        """Update the replay status text."""
        self._replay_label.config(text=f"Replay: {status}")

    def set_timer(self, text: str):
        """Update the timer display."""
        self._timer_label.config(text=text)
