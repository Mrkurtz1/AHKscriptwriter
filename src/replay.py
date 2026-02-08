"""Replay manager - executes AHK v2 scripts via AutoHotkey.exe."""

import os
import subprocess
import tempfile
import threading
from enum import Enum
from typing import Callable, Optional


class ReplayStatus(Enum):
    IDLE = "Idle"
    RUNNING = "Running"
    FINISHED = "Finished"
    ERROR = "Error"


class ReplayManager:
    """Executes AHK v2 script content through the AutoHotkey runtime."""

    def __init__(
        self,
        ahk_exe_path: str = "",
        on_status_change: Optional[Callable[[ReplayStatus, str], None]] = None,
    ):
        self.ahk_exe_path = ahk_exe_path
        self.on_status_change = on_status_change
        self._status = ReplayStatus.IDLE
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def status(self) -> ReplayStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status == ReplayStatus.RUNNING

    def find_ahk_exe(self) -> str:
        """Locate AutoHotkey.exe on the system."""
        if self.ahk_exe_path and os.path.isfile(self.ahk_exe_path):
            return self.ahk_exe_path

        # Common installation paths
        search_paths = [
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "AutoHotkey", "v2", "AutoHotkey.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "AutoHotkey", "AutoHotkey.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "AutoHotkey", "v2", "AutoHotkey.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "AutoHotkey", "AutoHotkey.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "AutoHotkey", "v2", "AutoHotkey.exe"),
        ]

        for path in search_paths:
            if os.path.isfile(path):
                self.ahk_exe_path = path
                return path

        # Try PATH
        try:
            result = subprocess.run(
                ["where", "AutoHotkey.exe"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().splitlines()[0]
                self.ahk_exe_path = path
                return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return ""

    def replay(self, script_text: str):
        """Execute the given AHK v2 script text asynchronously."""
        if self._status == ReplayStatus.RUNNING:
            self.stop()

        ahk_path = self.find_ahk_exe()
        if not ahk_path:
            self._set_status(
                ReplayStatus.ERROR,
                "AutoHotkey.exe not found. Install AutoHotkey v2 or set the path in Settings."
            )
            return

        self._thread = threading.Thread(
            target=self._run_script, args=(ahk_path, script_text), daemon=True
        )
        self._thread.start()

    def _run_script(self, ahk_path: str, script_text: str):
        """Run the script in a subprocess (called from a background thread)."""
        tmp_file = None
        try:
            self._set_status(ReplayStatus.RUNNING, "Replay started...")

            # Write script to a temp file
            tmp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".ahk", delete=False, encoding="utf-8"
            )
            tmp_file.write(script_text)
            tmp_file.close()

            self._process = subprocess.Popen(
                [ahk_path, tmp_file.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout, stderr = self._process.communicate()
            exit_code = self._process.returncode

            if exit_code == 0:
                msg = "Replay finished successfully."
                if stdout.strip():
                    msg += f"\nOutput: {stdout.strip()}"
                self._set_status(ReplayStatus.FINISHED, msg)
            else:
                msg = f"Replay exited with code {exit_code}."
                if stderr.strip():
                    msg += f"\nError: {stderr.strip()}"
                elif stdout.strip():
                    msg += f"\nOutput: {stdout.strip()}"
                self._set_status(ReplayStatus.ERROR, msg)

        except FileNotFoundError:
            self._set_status(
                ReplayStatus.ERROR,
                f"AutoHotkey executable not found at: {ahk_path}"
            )
        except Exception as e:
            self._set_status(ReplayStatus.ERROR, f"Replay error: {e}")
        finally:
            self._process = None
            if tmp_file and os.path.exists(tmp_file.name):
                try:
                    os.unlink(tmp_file.name)
                except OSError:
                    pass

    def stop(self):
        """Stop the currently running replay."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self._process.kill()
                except OSError:
                    pass
            self._process = None
            self._set_status(ReplayStatus.FINISHED, "Replay stopped by user.")

    def _set_status(self, status: ReplayStatus, message: str = ""):
        self._status = status
        if self.on_status_change:
            self.on_status_change(status, message)
