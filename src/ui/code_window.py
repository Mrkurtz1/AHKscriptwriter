"""Code editor panel - displays and edits generated AHK v2 code."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional


class FindBar(ttk.Frame):
    """Simple find bar for the code editor."""

    def __init__(self, parent, text_widget: tk.Text, **kwargs):
        super().__init__(parent, **kwargs)
        self.text_widget = text_widget
        self._visible = False
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text="Find:").pack(side=tk.LEFT, padx=(5, 2))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=2)
        self.search_entry.bind("<Return>", lambda e: self.find_next())

        ttk.Button(self, text="Next", command=self.find_next, width=6).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(self, text="Prev", command=self.find_prev, width=6).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(self, text="Close", command=self.hide, width=6).pack(
            side=tk.LEFT, padx=2
        )

        self._match_label = ttk.Label(self, text="")
        self._match_label.pack(side=tk.LEFT, padx=5)

    def show(self):
        """Show the find bar and focus the search entry."""
        if not self._visible:
            self.pack(fill=tk.X, before=self.master.winfo_children()[0])
            self._visible = True
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def hide(self):
        """Hide the find bar."""
        if self._visible:
            self.pack_forget()
            self._visible = False
            self.text_widget.tag_remove("search_highlight", "1.0", tk.END)
            self.text_widget.tag_remove("search_current", "1.0", tk.END)

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    def find_next(self):
        self._find(forwards=True)

    def find_prev(self):
        self._find(forwards=False)

    def _find(self, forwards=True):
        query = self.search_var.get()
        if not query:
            return

        self.text_widget.tag_remove("search_highlight", "1.0", tk.END)
        self.text_widget.tag_remove("search_current", "1.0", tk.END)

        # Highlight all matches
        count_var = tk.IntVar()
        match_count = 0
        start = "1.0"
        while True:
            pos = self.text_widget.search(
                query, start, stopindex=tk.END, nocase=True, count=count_var
            )
            if not pos:
                break
            end = f"{pos}+{count_var.get()}c"
            self.text_widget.tag_add("search_highlight", pos, end)
            start = end
            match_count += 1

        if match_count == 0:
            self._match_label.config(text="No matches")
            return

        self._match_label.config(text=f"{match_count} match(es)")

        # Find next/prev from current cursor
        cursor = self.text_widget.index(tk.INSERT)
        if forwards:
            pos = self.text_widget.search(
                query, f"{cursor}+1c", stopindex=tk.END, nocase=True, count=count_var
            )
            if not pos:
                pos = self.text_widget.search(
                    query, "1.0", stopindex=tk.END, nocase=True, count=count_var
                )
        else:
            pos = self.text_widget.search(
                query, cursor, stopindex="1.0", backwards=True, nocase=True, count=count_var
            )
            if not pos:
                pos = self.text_widget.search(
                    query, tk.END, stopindex="1.0", backwards=True, nocase=True, count=count_var
                )

        if pos:
            end = f"{pos}+{count_var.get()}c"
            self.text_widget.tag_add("search_current", pos, end)
            self.text_widget.mark_set(tk.INSERT, pos)
            self.text_widget.see(pos)


class CodeWindowPanel(ttk.Frame):
    """Right panel with the AHK v2 code editor."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self):
        # Header with action buttons
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=tk.X, padx=5, pady=(5, 2))

        ttk.Label(header_frame, text="Code Window", font=("Segoe UI", 10, "bold")).pack(
            side=tk.LEFT
        )

        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="Save As...", command=self.save_as, width=8).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(btn_frame, text="Load...", command=self.load_file, width=8).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(btn_frame, text="Clear", command=self.clear, width=6).pack(
            side=tk.LEFT, padx=2
        )

        # Text editor with scrollbar
        editor_frame = ttk.Frame(self)
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.text = tk.Text(
            editor_frame,
            wrap=tk.NONE,
            font=("Consolas", 10),
            undo=True,
            maxundo=-1,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#ffffff",
            selectbackground="#264f78",
            selectforeground="#ffffff",
            padx=8,
            pady=8,
        )

        # Scrollbars
        y_scroll = ttk.Scrollbar(editor_frame, orient=tk.VERTICAL, command=self.text.yview)
        x_scroll = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL, command=self.text.xview)
        self.text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        editor_frame.grid_rowconfigure(0, weight=1)
        editor_frame.grid_columnconfigure(0, weight=1)

        # Search highlight tags
        self.text.tag_configure("search_highlight", background="#613214")
        self.text.tag_configure("search_current", background="#9e6a03")

        # Find bar (hidden by default)
        self.find_bar = FindBar(self, self.text)

        # Keyboard shortcuts
        self.text.bind("<Control-f>", lambda e: self.find_bar.toggle())
        self.text.bind("<Control-z>", lambda e: self._undo())
        self.text.bind("<Control-y>", lambda e: self._redo())
        self.text.bind("<Control-Shift-Z>", lambda e: self._redo())

    def get_text(self) -> str:
        """Get the full text content."""
        return self.text.get("1.0", tk.END).rstrip("\n")

    def set_text(self, content: str):
        """Replace the entire text content."""
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.text.edit_reset()

    def append_text(self, content: str):
        """Append text at the end."""
        self.text.insert(tk.END, content)
        self.text.see(tk.END)

    def clear(self):
        """Clear the editor content."""
        self.text.delete("1.0", tk.END)
        self.text.edit_reset()

    def save_as(self):
        """Save the content to a file."""
        path = filedialog.asksaveasfilename(
            defaultextension=".ahk",
            filetypes=[("AHK Scripts", "*.ahk"), ("All Files", "*.*")],
            title="Save Script As",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.get_text())
            except OSError as e:
                messagebox.showerror("Save Error", f"Could not save file:\n{e}")

    def load_file(self):
        """Load a script file into the editor."""
        path = filedialog.askopenfilename(
            filetypes=[("AHK Scripts", "*.ahk"), ("Text Files", "*.txt"), ("All Files", "*.*")],
            title="Load Script",
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.set_text(content)
            except OSError as e:
                messagebox.showerror("Load Error", f"Could not load file:\n{e}")

    def _undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            pass

    def _redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass
