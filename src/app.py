"""Main application window - wires together all components."""

import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional

from src.models import RecordedEvent, RecordingState, Session
from src.settings import SettingsManager
from src.recorder import Recorder
from src.code_generator import CodeGenerator
from src.replay import ReplayManager, ReplayStatus
from src.ui.toolbar import Toolbar
from src.ui.event_log import EventLogPanel
from src.ui.code_window import CodeWindowPanel
from src.ui.status_bar import StatusBar
from src.ui.settings_dialog import SettingsDialog


def _get_tk_hwnd(root: tk.Tk) -> int:
    """Get the Win32 HWND of the tkinter root window (Windows only)."""
    try:
        import ctypes
        return ctypes.windll.user32.GetParent(root.winfo_id())
    except Exception:
        return 0


class AHKMacroBuilderApp:
    """Main application class orchestrating the AHK Macro Builder."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AHK Macro Builder")
        self.root.geometry("1100x700")
        self.root.minsize(800, 500)

        # Core components
        self.settings_manager = SettingsManager()
        self.settings_manager.load()
        self.settings = self.settings_manager.settings

        self.code_generator = CodeGenerator(self.settings)
        self.sessions: List[Session] = []

        self.recorder = Recorder(
            settings=self.settings,
            on_event=self._on_event_recorded,
            on_state_change=self._on_recording_state_change,
            get_own_hwnd=lambda: _get_tk_hwnd(self.root),
        )

        self.replay_manager = ReplayManager(
            ahk_exe_path=self.settings.ahk_exe_path,
            on_status_change=self._on_replay_status_change,
        )

        # Recording timer
        self._recording_start_time: Optional[float] = None
        self._timer_after_id: Optional[str] = None

        self._build_ui()
        self._apply_settings()
        self._bind_hotkeys()

    def _build_ui(self):
        """Build the main application layout."""
        # Toolbar
        self.toolbar = Toolbar(
            self.root,
            on_start=self._start_recording,
            on_stop=self._stop_recording,
            on_pause=self._pause_resume_recording,
            on_replay=self._start_replay,
            on_stop_replay=self._stop_replay,
            on_settings=self._open_settings,
        )
        self.toolbar.pack(fill=tk.X)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # Main content - split pane
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left: Event log
        self.event_log = EventLogPanel(paned)
        paned.add(self.event_log, weight=1)

        # Right: Code window
        self.code_window = CodeWindowPanel(paned)
        paned.add(self.code_window, weight=2)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # Status bar
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _bind_hotkeys(self):
        """Register global keyboard shortcuts."""
        self.root.bind_all("<Control-Shift-P>", self._on_abort_replay_hotkey)
        self.root.bind_all("<Control-Shift-p>", self._on_abort_replay_hotkey)

    def _on_abort_replay_hotkey(self, event=None):
        """Handle Ctrl+Shift+P to abort a running replay."""
        if self.replay_manager.is_running:
            self._stop_replay()

    def _apply_settings(self):
        """Apply current settings to UI and components."""
        self.status_bar.set_coord_mode(self.settings.coord_mode)
        self.code_generator = CodeGenerator(self.settings)
        self.replay_manager.ahk_exe_path = self.settings.ahk_exe_path

    def _refresh_macro_list(self):
        """Parse the code window and update the macro selector dropdown."""
        script_text = self.code_window.get_text()
        names = ReplayManager.extract_macro_names(script_text)
        self.toolbar.update_macro_list(names)

    # ---- Recording ----

    def _start_recording(self):
        """Start a new recording session."""
        session = self.recorder.start_recording()
        self.sessions.append(session)
        self._recording_start_time = time.time()
        self._update_timer()

    def _stop_recording(self):
        """Stop the current recording session."""
        session = self.recorder.stop_recording()
        self._cancel_timer()

        if session and session.events:
            # Generate code for this session and append to code window
            new_code = self.code_generator.append_subroutine_to_script(
                self.code_window.get_text(), session
            )
            self.code_window.set_text(new_code)
            self._refresh_macro_list()

    def _pause_resume_recording(self):
        """Toggle pause/resume on the current recording."""
        if self.recorder.state == RecordingState.RECORDING:
            self.recorder.pause_recording()
        elif self.recorder.state == RecordingState.PAUSED:
            self.recorder.resume_recording()

    def _on_event_recorded(self, event: RecordedEvent):
        """Callback when a new event is recorded (called from listener thread)."""
        # Schedule UI updates on the main thread
        self.root.after(0, self._handle_recorded_event, event)

    def _handle_recorded_event(self, event: RecordedEvent):
        """Process a recorded event on the main thread."""
        self.event_log.add_event(event)

        # Update status bar
        color = event.color1 or "N/A"
        self.status_bar.set_last_capture(event.x1, event.y1, color)

    def _on_recording_state_change(self, state: RecordingState):
        """Callback when recording state changes (called from recorder thread)."""
        self.root.after(0, self._handle_state_change, state)

    def _handle_state_change(self, state: RecordingState):
        """Update UI for recording state changes on the main thread."""
        self.status_bar.set_recording_state(state)

        if state == RecordingState.RECORDING:
            self.toolbar.set_recording_state(True, False)
        elif state == RecordingState.PAUSED:
            self.toolbar.set_recording_state(True, True)
        else:
            self.toolbar.set_recording_state(False)

    # ---- Timer ----

    def _update_timer(self):
        """Update the recording duration timer."""
        if self._recording_start_time and self.recorder.state != RecordingState.IDLE:
            elapsed = time.time() - self._recording_start_time
            mins, secs = divmod(int(elapsed), 60)
            self.status_bar.set_timer(f"{mins:02d}:{secs:02d}")
            self._timer_after_id = self.root.after(1000, self._update_timer)

    def _cancel_timer(self):
        """Cancel the recording timer."""
        if self._timer_after_id:
            self.root.after_cancel(self._timer_after_id)
            self._timer_after_id = None
        self.status_bar.set_timer("")

    # ---- Replay ----

    def _start_replay(self):
        """Replay the current code window content (or selected macro)."""
        if self.recorder.state != RecordingState.IDLE:
            messagebox.showwarning(
                "Recording Active",
                "Please stop recording before starting replay."
            )
            return

        script_text = self.code_window.get_text()
        if not script_text.strip():
            messagebox.showinfo("Empty Script", "There is no script to replay.")
            return

        # Refresh macro list before replay in case user edited the code
        self._refresh_macro_list()

        selected_macro = self.toolbar.get_selected_macro()
        self.replay_manager.replay(script_text, macro_name=selected_macro)

    def _stop_replay(self):
        """Stop the currently running replay."""
        self.replay_manager.stop()

    def _on_replay_status_change(self, status: ReplayStatus, message: str):
        """Callback when replay status changes (called from replay thread)."""
        self.root.after(0, self._handle_replay_status, status, message)

    def _handle_replay_status(self, status: ReplayStatus, message: str):
        """Update UI for replay status on the main thread."""
        self.status_bar.set_replay_status(status.value)
        self.toolbar.set_replay_state(status == ReplayStatus.RUNNING)

        if status == ReplayStatus.RUNNING:
            self.status_bar.set_replay_command(self.replay_manager.last_command)
        else:
            self.status_bar.set_replay_command("")

        if status == ReplayStatus.ERROR:
            messagebox.showerror("Replay Error", message)
        elif status == ReplayStatus.FINISHED and message:
            self.status_bar.set_replay_status(message.split("\n")[0])

    # ---- Settings ----

    def _open_settings(self):
        """Open the settings dialog."""
        SettingsDialog(self.root, self.settings, on_save=self._on_settings_saved)

    def _on_settings_saved(self, new_settings):
        """Apply updated settings."""
        self.settings = new_settings
        self.settings_manager.settings = new_settings
        self.settings_manager.save()
        self._apply_settings()

        # Update recorder settings too
        self.recorder.settings = new_settings

    # ---- Run ----

    def run(self):
        """Start the application main loop."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        """Clean up and close the application."""
        # Stop recording if active
        if self.recorder.state != RecordingState.IDLE:
            self.recorder.stop_recording()

        # Stop replay if running
        if self.replay_manager.is_running:
            self.replay_manager.stop()

        self._cancel_timer()
        self.root.destroy()
