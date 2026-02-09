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
    CoordMode,
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
# and foreground window title detection (for Window mode auto-capture)
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

    def get_foreground_window_title() -> str:
        """Return the title of the current foreground window."""
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

except (ImportError, AttributeError, OSError):
    def _get_window_under_cursor(x: int, y: int) -> int:
        return 0

    def _get_foreground_hwnd() -> int:
        return 0

    def get_foreground_window_title() -> str:
        return ""


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

            coord_mode = self.settings.get_coord_mode()

            # In Window/Client mode, capture the target window title
            # Use manual override from settings if provided, otherwise auto-detect
            if coord_mode in (CoordMode.WINDOW, CoordMode.CLIENT):
                if self.settings.target_window_title:
                    target_title = self.settings.target_window_title
                else:
                    target_title = get_foreground_window_title()
            else:
                target_title = ""

            self._current_session = Session(
                id=self._session_counter,
                name=name,
                coord_mode=coord_mode,
                target_window_title=target_title,
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
            ancestor_click = ctypes.windll.user32.GetAncestor(click_hwnd, 2)  # GA_ROOT
            ancestor_own = ctypes.windll.user32.GetAncestor(own_hwnd, 2)
            return ancestor_click == ancestor_own
        except Exception:
            return False

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

    def _on_click(self, x: int, y: int, button, pressed: bool):
        """Handle mouse button press/release."""
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

    def _on_key_press(self, key):
        """Handle keyboard key press."""
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

    def _emit_event(self, event: RecordedEvent):
        """Add event to session and notify callback."""
        if self._current_session:
            self._current_session.add_event(event)
        if self.on_event:
            self.on_event(event)
