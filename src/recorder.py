"""Mouse event recorder with drag detection and pixel color capture."""

import math
import time
import threading
from datetime import datetime
from typing import Callable, Optional

try:
    from pynput import mouse, keyboard as pynput_keyboard
    _PYNPUT_AVAILABLE = True
except ImportError:
    _PYNPUT_AVAILABLE = False
    mouse = None  # type: ignore
    pynput_keyboard = None  # type: ignore

from src.models import (
    EventType,
    MouseButton,
    RecordedEvent,
    RecordingState,
    Session,
)
from src.settings import AppSettings

# Platform-specific pixel color capture
try:
    import ctypes
    from ctypes import windll

    def get_pixel_color(x: int, y: int) -> str:
        """Capture pixel color at (x, y) using Windows GDI."""
        hdc = windll.user32.GetDC(0)
        pixel = windll.gdi32.GetPixel(hdc, x, y)
        windll.user32.ReleaseDC(0, hdc)
        if pixel == -1:
            return "0x000000"
        r = pixel & 0xFF
        g = (pixel >> 8) & 0xFF
        b = (pixel >> 16) & 0xFF
        return f"0x{r:02X}{g:02X}{b:02X}"
except (ImportError, AttributeError, OSError):
    # Fallback for non-Windows (development) environments
    try:
        from PIL import ImageGrab

        def get_pixel_color(x: int, y: int) -> str:
            """Capture pixel color using Pillow screen grab."""
            try:
                img = ImageGrab.grab(bbox=(x, y, x + 1, y + 1))
                r, g, b = img.getpixel((0, 0))[:3]
                return f"0x{r:02X}{g:02X}{b:02X}"
            except Exception:
                return "0x000000"
    except ImportError:
        def get_pixel_color(x: int, y: int) -> str:
            return "0x000000"


# Platform-specific window-under-cursor detection (for ignore-own-clicks)
try:
    import ctypes as _ct

    def _get_window_under_cursor(x: int, y: int) -> int:
        """Return the HWND of the window under the given screen coordinates."""
        import ctypes
        point = ctypes.wintypes.POINT(x, y)
        return ctypes.windll.user32.WindowFromPoint(point)

    def _get_foreground_hwnd() -> int:
        import ctypes
        return ctypes.windll.user32.GetForegroundWindow()

    def _get_root_hwnd(hwnd: int) -> int:
        """Return the top-level owner window HWND for a given handle.

        Uses GA_ROOTOWNER (3) instead of GA_ROOT (2) so that owned
        sub-windows / frames are resolved to the main application
        window.  GA_ROOT only walks the *parent* chain and stops at
        owned top-level frames, which causes coordinates to be computed
        relative to the frame rather than the outer application window.
        """
        import ctypes
        if hwnd == 0:
            return 0
        root = ctypes.windll.user32.GetAncestor(hwnd, 3)  # GA_ROOTOWNER
        return root if root else hwnd

    def _get_window_title(hwnd: int) -> str:
        """Return the window title for the given HWND."""
        import ctypes
        if hwnd == 0:
            return ""
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def _get_window_origin(hwnd: int) -> tuple:
        """Return (left, top) screen position of the window's outer frame."""
        import ctypes
        if hwnd == 0:
            return (0, 0)
        rect = ctypes.wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return (0, 0)
        return (rect.left, rect.top)

    def _screen_to_window(hwnd: int, x: int, y: int) -> tuple:
        """Convert screen coordinates to window-relative coordinates."""
        left, top = _get_window_origin(hwnd)
        return (x - left, y - top)

    def _screen_to_client(hwnd: int, x: int, y: int) -> tuple:
        """Convert screen coordinates to client-area-relative coordinates."""
        import ctypes
        point = ctypes.wintypes.POINT(x, y)
        if not ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point)):
            return (x, y)
        return (point.x, point.y)

    def _window_rect_contains(hwnd: int, x: int, y: int) -> bool:
        """Return True if screen point (x, y) lies within *hwnd*'s window rect.

        Used to verify that a mouse click falls inside the foreground window
        so we can use it as the coordinate reference instead of relying on
        WindowFromPoint, which may return nested child / frame HWNDs.
        """
        import ctypes
        if hwnd == 0:
            return False
        rect = ctypes.wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        return rect.left <= x <= rect.right and rect.top <= y <= rect.bottom

    def _find_app_window_at_point(x: int, y: int, exclude_hwnd: int = 0) -> int:
        """Find the main application window containing screen point (x, y).

        Enumerates top-level windows in z-order and returns the first
        visible window with a title bar (``WS_CAPTION``) whose rectangle
        contains the given point.

        Nested content windows (embedded browser controls, framework panels,
        etc.) are typically top-level windows with **no** formal parent/owner
        chain back to the main application window **and** no title bar.
        By requiring ``WS_CAPTION`` this function skips them and finds the
        actual application frame instead.

        Parameters:
            x, y: Screen coordinates of the click.
            exclude_hwnd: HWND to skip (e.g. the recorder tool's own window).
        """
        import ctypes
        from ctypes import wintypes

        GWL_STYLE = -16
        WS_CAPTION = 0x00C00000
        result = [0]

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, _lparam):
            hwnd_val = int(hwnd) if hwnd else 0
            if hwnd_val == 0:
                return True
            if exclude_hwnd and hwnd_val == exclude_hwnd:
                return True
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True

            rect = wintypes.RECT()
            if not ctypes.windll.user32.GetWindowRect(
                hwnd, ctypes.byref(rect)
            ):
                return True

            if not (
                rect.left <= x <= rect.right and rect.top <= y <= rect.bottom
            ):
                return True

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            if (style & WS_CAPTION) == WS_CAPTION:
                result[0] = hwnd_val
                return False  # found -- stop enumeration

            return True

        ctypes.windll.user32.EnumWindows(_enum_cb, 0)
        return result[0]

except (ImportError, AttributeError, OSError):
    def _get_window_under_cursor(x: int, y: int) -> int:
        return 0

    def _get_foreground_hwnd() -> int:
        return 0

    def _get_root_hwnd(hwnd: int) -> int:
        return hwnd

    def _get_window_title(hwnd: int) -> str:
        return ""

    def _get_window_origin(hwnd: int) -> tuple:
        return (0, 0)

    def _screen_to_window(hwnd: int, x: int, y: int) -> tuple:
        return (x, y)

    def _screen_to_client(hwnd: int, x: int, y: int) -> tuple:
        return (x, y)

    def _window_rect_contains(hwnd: int, x: int, y: int) -> bool:
        return False

    def _find_app_window_at_point(x: int, y: int, exclude_hwnd: int = 0) -> int:
        return 0


def _pynput_button_to_model(button) -> Optional[MouseButton]:
    """Convert a pynput Button to our MouseButton enum."""
    name = button.name if hasattr(button, "name") else str(button)
    mapping = {
        "left": MouseButton.LEFT,
        "right": MouseButton.RIGHT,
        "middle": MouseButton.MIDDLE,
    }
    return mapping.get(name)


class Recorder:
    """Records mouse events and produces RecordedEvent objects.

    Handles click detection, drag detection (based on a pixel threshold),
    optional mouse movement recording, and keystroke recording.
    """

    def __init__(
        self,
        settings: AppSettings,
        on_event: Optional[Callable[[RecordedEvent], None]] = None,
        on_state_change: Optional[Callable[[RecordingState], None]] = None,
        get_own_hwnd: Optional[Callable[[], int]] = None,
    ):
        self.settings = settings
        self.on_event = on_event
        self.on_state_change = on_state_change
        self.get_own_hwnd = get_own_hwnd  # callback to get the app's own window handle

        self._state = RecordingState.IDLE
        self._session_counter = 0
        self._current_session: Optional[Session] = None

        # Drag tracking state
        self._press_info: dict = {}  # button -> (x, y, time, color)
        self._drag_active: dict = {}  # button -> bool
        self._current_pos = (0, 0)

        # Movement recording
        self._last_move_time = 0.0
        self._last_move_pos = (0, 0)

        # Listeners
        self._mouse_listener = None
        self._keyboard_listener = None
        self._lock = threading.Lock()

    @property
    def state(self) -> RecordingState:
        return self._state

    @property
    def current_session(self) -> Optional[Session]:
        return self._current_session

    def start_recording(self) -> Session:
        """Start a new recording session."""
        with self._lock:
            self._session_counter += 1

            if self.settings.macro_naming == "timestamp":
                name = f"{self.settings.macro_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            else:
                name = f"{self.settings.macro_prefix}_{self._session_counter:03d}"

            self._current_session = Session(
                id=self._session_counter,
                name=name,
                coord_mode=self.settings.get_coord_mode(),
            )
            self._press_info.clear()
            self._drag_active.clear()
            self._set_state(RecordingState.RECORDING)
            self._start_listeners()

        return self._current_session

    def stop_recording(self) -> Optional[Session]:
        """Stop recording and return the completed session."""
        with self._lock:
            self._stop_listeners()
            session = self._current_session
            self._set_state(RecordingState.IDLE)
        return session

    def pause_recording(self):
        """Pause recording (events are ignored while paused)."""
        with self._lock:
            if self._state == RecordingState.RECORDING:
                self._set_state(RecordingState.PAUSED)

    def resume_recording(self):
        """Resume recording from a paused state."""
        with self._lock:
            if self._state == RecordingState.PAUSED:
                self._set_state(RecordingState.RECORDING)

    def _set_state(self, new_state: RecordingState):
        self._state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)

    def _is_own_window(self, x: int, y: int) -> bool:
        """Check if the click is on the tool's own window."""
        if not self.settings.ignore_own_clicks:
            return False
        if not self.get_own_hwnd:
            return False
        try:
            own_hwnd = self.get_own_hwnd()
            if own_hwnd == 0:
                return False
            click_hwnd = _get_window_under_cursor(x, y)
            if click_hwnd == 0:
                return False
            # Check if the clicked window is the same as or a child of our own window
            import ctypes
            ancestor_click = ctypes.windll.user32.GetAncestor(click_hwnd, 3)  # GA_ROOTOWNER
            ancestor_own = ctypes.windll.user32.GetAncestor(own_hwnd, 3)  # GA_ROOTOWNER
            return ancestor_click == ancestor_own
        except Exception:
            return False

    def _is_own_hwnd(self, hwnd: int) -> bool:
        """Check if a HWND refers to this tool's window."""
        if not self.get_own_hwnd or hwnd == 0:
            return False
        try:
            own_hwnd = self.get_own_hwnd()
            if own_hwnd == 0:
                return False
            import ctypes
            ancestor_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 3)  # GA_ROOTOWNER
            ancestor_own = ctypes.windll.user32.GetAncestor(own_hwnd, 3)  # GA_ROOTOWNER
            return ancestor_hwnd == ancestor_own
        except Exception:
            return False

    def _apply_window_context(self, event: RecordedEvent):
        """Capture window title and convert coordinates for Window/Client mode.

        For Window or Client coordinate modes this method:
        1. Resolves the target window HWND for this event.
        2. Records the window title on the event so the code generator can
           emit WinActivate when the active window changes.
        3. Converts the event's screen coordinates to window-relative or
           client-relative values so the generated AHK script uses the
           correct offset regardless of where the window sits on screen.

        For mouse events the method uses ``EnumWindows`` to find the main
        application window at the click point.  This avoids coordinate
        errors caused by nested frames or embedded child windows that
        both ``WindowFromPoint`` and ``GetForegroundWindow`` may return
        and that ``GetAncestor(GA_ROOTOWNER)`` cannot always resolve back
        to the outer application window.
        """
        if self.settings.coord_mode not in ("Window", "Client"):
            return

        prefer_foreground = event.event_type == EventType.KEYSTROKE

        # Resolve the target window HWND
        if prefer_foreground:
            # Keystrokes: always use the foreground window.
            hwnd = _get_foreground_hwnd()
            hwnd = _get_root_hwnd(hwnd) if hwnd else 0
        else:
            # Mouse events: enumerate top-level windows to find the main
            # application window at the click point.  EnumWindows walks
            # the z-order and we pick the first visible window with a
            # title bar (WS_CAPTION) that contains the point.  Nested
            # content windows (browser controls, framework panels, etc.)
            # typically lack a title bar and are skipped automatically.
            own_hwnd = 0
            if self.get_own_hwnd:
                try:
                    own_hwnd = self.get_own_hwnd()
                    own_hwnd = _get_root_hwnd(own_hwnd) if own_hwnd else 0
                except Exception:
                    own_hwnd = 0
            hwnd = _find_app_window_at_point(
                event.x1, event.y1, exclude_hwnd=own_hwnd,
            )
            if hwnd == 0:
                # Fallback: foreground window (e.g. non-Windows platforms)
                fg = _get_foreground_hwnd()
                hwnd = _get_root_hwnd(fg) if fg else 0

        if hwnd == 0 or self._is_own_hwnd(hwnd):
            return

        # Capture window title
        title = _get_window_title(hwnd)
        if title:
            event.window_title = title
            if not self.settings.target_window_title:
                self.settings.target_window_title = title

        # Convert coordinates from screen to window-relative
        if self.settings.coord_mode == "Window":
            convert = _screen_to_window
        else:  # Client
            convert = _screen_to_client

        event.x1, event.y1 = convert(hwnd, event.x1, event.y1)
        if event.x2 is not None and event.y2 is not None:
            event.x2, event.y2 = convert(hwnd, event.x2, event.y2)

    def _start_listeners(self):
        """Start the pynput mouse and keyboard listeners."""
        if not _PYNPUT_AVAILABLE:
            raise RuntimeError(
                "pynput is not available. Install it with: pip install pynput"
            )
        self._stop_listeners()

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_move=self._on_move,
        )
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

        self._keyboard_listener = pynput_keyboard.Listener(
            on_press=self._on_key_press,
        )
        self._keyboard_listener.daemon = True
        self._keyboard_listener.start()

    def _stop_listeners(self):
        """Stop the pynput mouse and keyboard listeners."""
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener = None

    def _on_move(self, x: int, y: int):
        """Handle mouse movement."""
        try:
            self._current_pos = (x, y)

            if self._state != RecordingState.RECORDING:
                return

            # Check if any button is pressed - update drag tracking
            for button, info in list(self._press_info.items()):
                if not self._drag_active.get(button, False):
                    px, py = info[0], info[1]
                    dist = math.hypot(x - px, y - py)
                    if dist >= self.settings.drag_threshold_px:
                        self._drag_active[button] = True

            # Optional movement recording
            if not self.settings.record_mouse_moves:
                return

            now = time.time()
            elapsed_ms = (now - self._last_move_time) * 1000
            if elapsed_ms < self.settings.mouse_move_sample_ms:
                return

            dist = math.hypot(x - self._last_move_pos[0], y - self._last_move_pos[1])
            if dist < 2:
                return

            self._last_move_time = now
            self._last_move_pos = (x, y)

            event = RecordedEvent(
                timestamp=now,
                event_type=EventType.MOVE,
                button=MouseButton.LEFT,
                x1=x,
                y1=y,
            )
            self._emit_event(event)
        except Exception:
            pass  # Never let exceptions kill the pynput listener

    def _on_click(self, x: int, y: int, button, pressed: bool):
        """Handle mouse button press/release."""
        try:
            if self._state != RecordingState.RECORDING:
                return

            # Filter out clicks on our own window
            if pressed and self._is_own_window(x, y):
                return

            mb = _pynput_button_to_model(button)
            if mb is None:
                return

            if pressed:
                # Button pressed: record position and color, begin tracking
                color = get_pixel_color(x, y)
                self._press_info[mb] = (x, y, time.time(), color)
                self._drag_active[mb] = False
            else:
                # Button released
                info = self._press_info.pop(mb, None)
                if info is None:
                    return

                start_x, start_y, press_time, start_color = info
                is_drag = self._drag_active.pop(mb, False)

                if is_drag:
                    end_color = get_pixel_color(x, y)
                    event = RecordedEvent(
                        timestamp=press_time,
                        event_type=EventType.DRAG,
                        button=mb,
                        x1=start_x,
                        y1=start_y,
                        x2=x,
                        y2=y,
                        color1=start_color,
                        color2=end_color,
                    )
                else:
                    event = RecordedEvent(
                        timestamp=press_time,
                        event_type=EventType.CLICK,
                        button=mb,
                        x1=start_x,
                        y1=start_y,
                        color1=start_color,
                    )

                self._emit_event(event)
        except Exception:
            pass  # Never let exceptions kill the pynput listener

    def _on_key_press(self, key):
        """Handle keyboard key press."""
        try:
            if self._state != RecordingState.RECORDING:
                return

            # Convert key to string representation
            try:
                # Printable character keys
                key_text = repr(key.char) if hasattr(key, 'char') and key.char else str(key)
            except AttributeError:
                key_text = str(key)

            event = RecordedEvent(
                timestamp=time.time(),
                event_type=EventType.KEYSTROKE,
                button=MouseButton.LEFT,  # unused for keystrokes
                x1=self._current_pos[0],
                y1=self._current_pos[1],
                key_text=key_text,
            )
            self._emit_event(event)
        except Exception:
            pass  # Never let exceptions kill the pynput listener

    def _emit_event(self, event: RecordedEvent):
        """Add event to session and notify callback."""
        try:
            self._apply_window_context(event)
        except Exception:
            pass  # Emit event with unconverted coords rather than losing it
        if self._current_session:
            self._current_session.add_event(event)
        if self.on_event:
            self.on_event(event)
