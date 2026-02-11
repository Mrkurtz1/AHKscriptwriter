"""Event log panel - displays recorded events in human-readable form."""

import tkinter as tk
from tkinter import ttk
from typing import Optional

from src.models import RecordedEvent


class EventLogPanel(ttk.Frame):
    """Left panel showing a scrollable list of recorded events."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self):
        # Header
        header = ttk.Label(self, text="Event Log", font=("Segoe UI", 10, "bold"))
        header.pack(fill=tk.X, padx=5, pady=(5, 2))

        # Treeview for events
        columns = ("index", "type", "details")
        self.tree = ttk.Treeview(
            self, columns=columns, show="headings", selectmode="browse"
        )
        self.tree.heading("index", text="#")
        self.tree.heading("type", text="Type")
        self.tree.heading("details", text="Details")
        self.tree.column("index", width=40, stretch=False)
        self.tree.column("type", width=60, stretch=False)
        self.tree.column("details", width=250, stretch=True)

        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 5))

        self._event_count = 0

    def add_window_activation(self, title: str):
        """Insert a window activation marker in the log."""
        self._event_count += 1
        self.tree.insert(
            "",
            tk.END,
            values=(
                self._event_count,
                "Window",
                f"Activated: {title}",
            ),
        )
        # Auto-scroll to bottom
        children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])

    def add_event(self, event: RecordedEvent):
        """Append an event to the log."""
        self._event_count += 1
        self.tree.insert(
            "",
            tk.END,
            values=(
                self._event_count,
                event.event_type.value,
                event.description(),
            ),
        )
        # Auto-scroll to bottom
        children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])

    def clear(self):
        """Clear all events from the log."""
        self.tree.delete(*self.tree.get_children())
        self._event_count = 0
