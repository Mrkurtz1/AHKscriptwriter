"""Tests for recorder.py -- coordinate conversion, drag detection,
own-window filtering, error resilience, and edge cases.

Since the Windows ctypes APIs are unavailable on Linux, we mock the
platform-specific helpers and test the Recorder logic directly.
"""

import pytest
from unittest.mock import patch, MagicMock, call

from src.models import (
    EventType, MouseButton, RecordedEvent, RecordingState, CoordMode, Session,
)
from src.settings import AppSettings
from src.recorder import Recorder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recorder(coord_mode="Window", target_title=""):
    settings = AppSettings(
        coord_mode=coord_mode,
        target_window_title=target_title,
        ignore_own_clicks=True,
    )
    return Recorder(
        settings=settings,
        on_event=None,
        on_state_change=None,
        get_own_hwnd=lambda: 999,  # dummy own hwnd
    )


def _make_event(
    event_type=EventType.CLICK,
    x1=500, y1=600,
    x2=None, y2=None,
    key_text=None,
):
    return RecordedEvent(
        timestamp=1000.0,
        event_type=event_type,
        button=MouseButton.LEFT,
        x1=x1, y1=y1,
        x2=x2, y2=y2,
        key_text=key_text,
    )


class FakeButton:
    """Mimics a pynput mouse Button for testing."""
    def __init__(self, name):
        self.name = name


def _make_recording_recorder(coord_mode="Screen", ignore_own_clicks=False,
                              on_stop_hotkey=None):
    """Create a Recorder already in RECORDING state for event-flow tests.

    Uses Screen mode so _apply_window_context is a no-op (avoids
    needing to mock all the Windows API helpers).
    """
    events = []
    settings = AppSettings(
        coord_mode=coord_mode,
        ignore_own_clicks=ignore_own_clicks,
    )
    rec = Recorder(
        settings=settings,
        on_event=events.append,
        on_state_change=None,
        get_own_hwnd=None,
        on_stop_hotkey=on_stop_hotkey,
    )
    # Put recorder into recording state without starting real pynput listeners
    rec._state = RecordingState.RECORDING
    rec._current_session = Session(
        id=1, name="test", coord_mode=settings.get_coord_mode(),
    )
    return rec, events


# ---------------------------------------------------------------------------
# Coordinate conversion in Window mode
# ---------------------------------------------------------------------------

class TestWindowModeCoordinateConversion:
    """When coord_mode=Window, screen coords should be converted to
    window-relative by subtracting the window origin."""

    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_window", return_value=(100, 150))
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=12345)
    def test_click_coords_converted(self, mock_find, mock_root,
                                     mock_convert, mock_title):
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        mock_find.assert_called_once_with(500, 600, exclude_hwnd=999)
        mock_convert.assert_called_once_with(12345, 500, 600)
        assert event.x1 == 100
        assert event.y1 == 150
        assert event.window_title == "Notepad"

    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_window", side_effect=[(10, 20), (110, 220)])
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=12345)
    def test_drag_both_coords_converted(self, mock_find, mock_root,
                                         mock_convert, mock_title):
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(
            event_type=EventType.DRAG,
            x1=500, y1=600, x2=700, y2=800,
        )

        rec._apply_window_context(event)

        assert mock_convert.call_count == 2
        assert event.x1 == 10
        assert event.y1 == 20
        assert event.x2 == 110
        assert event.y2 == 220


# ---------------------------------------------------------------------------
# Coordinate conversion in Client mode
# ---------------------------------------------------------------------------

class TestClientModeCoordinateConversion:
    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_client", return_value=(80, 130))
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=12345)
    def test_client_mode_uses_screen_to_client(self, mock_find, mock_root,
                                                mock_convert, mock_title):
        rec = _make_recorder(coord_mode="Client")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        mock_convert.assert_called_once_with(12345, 500, 600)
        assert event.x1 == 80
        assert event.y1 == 130


# ---------------------------------------------------------------------------
# Screen mode -- no conversion
# ---------------------------------------------------------------------------

class TestScreenModeNoConversion:
    def test_screen_mode_skips_conversion(self):
        """Screen mode should not touch coordinates or window titles."""
        rec = _make_recorder(coord_mode="Screen")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        # Coordinates unchanged
        assert event.x1 == 500
        assert event.y1 == 600
        assert event.window_title is None


# ---------------------------------------------------------------------------
# Own-window filtering
# ---------------------------------------------------------------------------

class TestOwnWindowFiltering:
    @patch("src.recorder._get_window_title", return_value="AHK Macro Builder")
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=999)
    def test_own_window_hwnd_skips_conversion(self, mock_find, mock_root,
                                               mock_title):
        """When the resolved HWND is our own window, skip title and conversion."""
        rec = _make_recorder(coord_mode="Window")
        rec._is_own_hwnd = MagicMock(return_value=True)
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        assert event.x1 == 500  # unchanged
        assert event.y1 == 600
        assert event.window_title is None


# ---------------------------------------------------------------------------
# Fallback when _find_app_window_at_point returns 0
# ---------------------------------------------------------------------------

class TestFindAppWindowFallback:
    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", side_effect=lambda h: {12345: 12345, 999: 999}.get(h, h))
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._find_app_window_at_point", return_value=0)
    def test_fallback_to_foreground_when_enum_fails(self, mock_find, mock_fg,
                                                      mock_root, mock_convert,
                                                      mock_title):
        """If _find_app_window_at_point returns 0, fall back to foreground."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        mock_find.assert_called_once()
        # Fell back to foreground window
        mock_fg.assert_called_once()
        assert event.x1 == 50
        assert event.y1 == 50

    @patch("src.recorder._get_root_hwnd", return_value=0)
    @patch("src.recorder._get_foreground_hwnd", return_value=0)
    @patch("src.recorder._find_app_window_at_point", return_value=0)
    def test_all_zero_hwnd_skips_everything(self, mock_find, mock_fg,
                                             mock_root):
        """If all HWND lookups return 0, nothing should be modified."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        assert event.x1 == 500
        assert event.y1 == 600
        assert event.window_title is None


# ---------------------------------------------------------------------------
# Window title capture sets target_window_title on first event
# ---------------------------------------------------------------------------

class TestTargetWindowTitleAutoSet:
    @patch("src.recorder._get_window_title", return_value="FirstWindow")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=12345)
    def test_first_event_sets_target(self, mock_find, mock_root,
                                      mock_convert, mock_title):
        rec = _make_recorder(coord_mode="Window", target_title="")
        event = _make_event()

        rec._apply_window_context(event)

        assert rec.settings.target_window_title == "FirstWindow"

    @patch("src.recorder._get_window_title", return_value="SecondWindow")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=12345)
    def test_existing_target_not_overwritten(self, mock_find, mock_root,
                                              mock_convert, mock_title):
        rec = _make_recorder(coord_mode="Window", target_title="AlreadySet")
        event = _make_event()

        rec._apply_window_context(event)

        assert rec.settings.target_window_title == "AlreadySet"


# ---------------------------------------------------------------------------
# Empty window title handling
# ---------------------------------------------------------------------------

class TestEmptyWindowTitle:
    @patch("src.recorder._get_window_title", return_value="")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=12345)
    def test_empty_title_still_converts_coords(self, mock_find, mock_root,
                                                mock_convert, mock_title):
        """Even if title is empty, coordinates should still be converted."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        assert event.x1 == 50
        assert event.y1 == 50
        assert event.window_title is None  # empty string doesn't get set


# ---------------------------------------------------------------------------
# Keystroke events use foreground window
# ---------------------------------------------------------------------------

class TestKeystrokeUseForeground:
    @patch("src.recorder._get_window_title", return_value="Editor")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._find_app_window_at_point", return_value=99999)
    def test_keystroke_prefers_foreground(self, mock_find, mock_fg, mock_root,
                                          mock_convert, mock_title):
        """Keystroke events should use GetForegroundWindow, not EnumWindows."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(event_type=EventType.KEYSTROKE, key_text="'a'")

        rec._apply_window_context(event)

        # Should have called foreground directly
        mock_fg.assert_called()
        # _find_app_window_at_point should NOT be called for keystrokes
        mock_find.assert_not_called()
        assert event.window_title == "Editor"


# ---------------------------------------------------------------------------
# Nested frame / owned-window resolution -- EnumWindows approach
# ---------------------------------------------------------------------------

class TestNestedFrameResolution:
    """When clicking inside a frame (owned sub-window), coordinates should
    be relative to the main application window, not the frame.

    _find_app_window_at_point (EnumWindows) directly finds the main
    application window (which has WS_CAPTION), skipping nested content
    windows that lack a title bar.
    """

    @patch("src.recorder._get_window_title", return_value="MainApp")
    @patch("src.recorder._screen_to_window", return_value=(200, 100))
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=1000)
    def test_nested_frame_bypassed_via_enum(self, mock_find, mock_root,
                                             mock_convert, mock_title):
        """EnumWindows finds the main app window (1000) directly,
        skipping the nested frame entirely.  Coordinates are relative
        to the main application window."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=700, y1=500)

        rec._apply_window_context(event)

        mock_find.assert_called_once_with(700, 500, exclude_hwnd=999)
        mock_convert.assert_called_once_with(1000, 700, 500)
        assert event.x1 == 200
        assert event.y1 == 100
        assert event.window_title == "MainApp"

    @patch("src.recorder._get_window_title", return_value="MainApp")
    @patch("src.recorder._screen_to_window", side_effect=[(200, 100), (400, 300)])
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._find_app_window_at_point", return_value=1000)
    def test_drag_in_frame_uses_main_window_for_both_coords(
        self, mock_find, mock_root, mock_convert, mock_title,
    ):
        """Drag events inside a frame should convert both start and end
        coordinates relative to the main application window."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(
            event_type=EventType.DRAG,
            x1=700, y1=500, x2=900, y2=700,
        )

        rec._apply_window_context(event)

        assert mock_convert.call_count == 2
        assert event.x1 == 200
        assert event.y1 == 100
        assert event.x2 == 400
        assert event.y2 == 300


# ---------------------------------------------------------------------------
# Exclude own HWND from EnumWindows search
# ---------------------------------------------------------------------------

class TestExcludeOwnHwnd:
    """The recorder's own window should be excluded from the EnumWindows
    search so we don't accidentally use it for coordinate conversion."""

    @patch("src.recorder._get_window_title", return_value="TargetApp")
    @patch("src.recorder._screen_to_window", return_value=(10, 20))
    @patch("src.recorder._get_root_hwnd", side_effect=lambda h: {999: 999}.get(h, h))
    @patch("src.recorder._find_app_window_at_point", return_value=8888)
    def test_own_hwnd_passed_as_exclude(self, mock_find, mock_root,
                                         mock_convert, mock_title):
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=300, y1=400)

        rec._apply_window_context(event)

        # The exclude_hwnd should be the root of the tool's own HWND
        mock_find.assert_called_once_with(300, 400, exclude_hwnd=999)
        assert event.x1 == 10
        assert event.y1 == 20


# ===========================================================================
# REGRESSION TESTS -- drag detection, click/drag flow, edge cases
# ===========================================================================


# ---------------------------------------------------------------------------
# Drag detection -- complete press → move → release flow
# ---------------------------------------------------------------------------

class TestDragDetection:
    """End-to-end drag detection via the internal callback methods."""

    @patch("src.recorder.get_pixel_color", return_value="0xFF0000")
    def test_drag_above_threshold(self, _mock_color):
        """Movement > drag_threshold_px produces a DRAG event."""
        rec, events = _make_recording_recorder()
        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(160, 100)  # 60px > default 10px threshold
        rec._on_click(160, 100, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.DRAG
        assert (events[0].x1, events[0].y1) == (100, 100)
        assert (events[0].x2, events[0].y2) == (160, 100)

    @patch("src.recorder.get_pixel_color", return_value="0x00FF00")
    def test_click_below_threshold(self, _mock_color):
        """Movement < drag_threshold_px produces a CLICK event."""
        rec, events = _make_recording_recorder()
        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(105, 100)  # 5px < 10px threshold
        rec._on_click(105, 100, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.CLICK
        assert (events[0].x1, events[0].y1) == (100, 100)
        assert events[0].x2 is None

    @patch("src.recorder.get_pixel_color", return_value="0x0000FF")
    def test_click_no_movement(self, _mock_color):
        """Press and release at same position is a CLICK."""
        rec, events = _make_recording_recorder()
        rec._on_click(200, 300, FakeButton("left"), True)
        rec._on_click(200, 300, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.CLICK
        assert (events[0].x1, events[0].y1) == (200, 300)

    @patch("src.recorder.get_pixel_color", return_value="0xABCDEF")
    def test_drag_at_exact_threshold(self, _mock_color):
        """Movement == drag_threshold_px counts as a DRAG (>=)."""
        rec, events = _make_recording_recorder()
        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(110, 100)  # exactly 10px = threshold
        rec._on_click(110, 100, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.DRAG

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_right_button_drag(self, _mock_color):
        """Right-button drag is detected the same way."""
        rec, events = _make_recording_recorder()
        rec._on_click(50, 50, FakeButton("right"), True)
        rec._on_move(200, 200, )  # well above threshold
        rec._on_click(200, 200, FakeButton("right"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.DRAG
        assert events[0].button == MouseButton.RIGHT
        assert (events[0].x1, events[0].y1) == (50, 50)
        assert (events[0].x2, events[0].y2) == (200, 200)

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_drag_captures_start_and_end_colors(self, mock_color):
        """Drag events record pixel colors at press and release points."""
        mock_color.side_effect = ["0xAAAAAA", "0xBBBBBB"]
        rec, events = _make_recording_recorder()
        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(200, 200)
        rec._on_click(200, 200, FakeButton("left"), False)

        assert events[0].color1 == "0xAAAAAA"
        assert events[0].color2 == "0xBBBBBB"

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_diagonal_drag(self, _mock_color):
        """Diagonal movement uses Euclidean distance for threshold check."""
        rec, events = _make_recording_recorder()
        # sqrt(7^2 + 7^2) ≈ 9.9 < 10 threshold → should be CLICK
        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(107, 107)
        rec._on_click(107, 107, FakeButton("left"), False)

        assert events[0].event_type == EventType.CLICK

        # sqrt(8^2 + 8^2) ≈ 11.3 >= 10 threshold → should be DRAG
        events.clear()
        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(108, 108)
        rec._on_click(108, 108, FakeButton("left"), False)

        assert events[0].event_type == EventType.DRAG


# ---------------------------------------------------------------------------
# Simultaneous multi-button presses
# ---------------------------------------------------------------------------

class TestMultiButtonTracking:
    """Multiple mouse buttons pressed simultaneously are tracked independently."""

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_left_and_right_independent(self, _mock_color):
        """Pressing left then right, releasing in different order."""
        rec, events = _make_recording_recorder()

        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_click(200, 200, FakeButton("right"), True)
        rec._on_move(300, 300)  # both buttons move
        rec._on_click(300, 300, FakeButton("left"), False)
        rec._on_click(300, 300, FakeButton("right"), False)

        assert len(events) == 2
        # Both should be DRAGs (moved well beyond threshold)
        assert events[0].button == MouseButton.LEFT
        assert events[0].event_type == EventType.DRAG
        assert events[0].x1 == 100  # left started at 100
        assert events[1].button == MouseButton.RIGHT
        assert events[1].event_type == EventType.DRAG
        assert events[1].x1 == 200  # right started at 200

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_unknown_button_ignored(self, _mock_color):
        """Buttons not in LEFT/RIGHT/MIDDLE mapping are silently ignored."""
        rec, events = _make_recording_recorder()
        rec._on_click(100, 100, FakeButton("x2"), True)
        rec._on_click(100, 100, FakeButton("x2"), False)

        assert len(events) == 0


# ---------------------------------------------------------------------------
# State checks -- IDLE and PAUSED states suppress events
# ---------------------------------------------------------------------------

class TestRecordingStateChecks:
    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_idle_state_ignores_clicks(self, _mock_color):
        """Events while IDLE are not captured."""
        rec, events = _make_recording_recorder()
        rec._state = RecordingState.IDLE

        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_click(100, 100, FakeButton("left"), False)
        assert len(events) == 0

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_paused_state_ignores_clicks(self, _mock_color):
        """Events while PAUSED are not captured."""
        rec, events = _make_recording_recorder()
        rec._state = RecordingState.PAUSED

        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_click(100, 100, FakeButton("left"), False)
        assert len(events) == 0

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_paused_during_drag_loses_drag(self, _mock_color):
        """If recording is paused between press and release, release is
        ignored because the press was never recorded (state was changed)."""
        rec, events = _make_recording_recorder()

        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(200, 200)  # drag tracking updates

        # Pause recording before release
        rec._state = RecordingState.PAUSED
        rec._on_click(200, 200, FakeButton("left"), False)

        # Release during pause is ignored → no event emitted
        assert len(events) == 0

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_resume_after_stale_press_starts_fresh(self, _mock_color):
        """After pause/resume, a new press overwrites stale _press_info."""
        rec, events = _make_recording_recorder()

        # Press during recording, then pause
        rec._on_click(100, 100, FakeButton("left"), True)
        rec._state = RecordingState.PAUSED

        # Resume and do a new click at different coords
        rec._state = RecordingState.RECORDING
        rec._on_click(500, 500, FakeButton("left"), True)
        rec._on_click(500, 500, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.CLICK
        assert (events[0].x1, events[0].y1) == (500, 500)


# ---------------------------------------------------------------------------
# Release without prior press (e.g. recording started mid-drag)
# ---------------------------------------------------------------------------

class TestOrphanRelease:
    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_release_without_press_ignored(self, _mock_color):
        """If a release arrives with no matching press, it is safely ignored."""
        rec, events = _make_recording_recorder()
        rec._on_click(100, 100, FakeButton("left"), False)

        assert len(events) == 0


# ---------------------------------------------------------------------------
# Own-window filtering on click events
# ---------------------------------------------------------------------------

class TestOwnWindowClickFilter:
    """The _is_own_window check filters presses on the recorder's window
    but does NOT filter releases, allowing drags that end on the recorder."""

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_press_on_own_window_filtered(self, _mock_color):
        """Press on own window is silently filtered -- no event emitted."""
        rec, events = _make_recording_recorder(ignore_own_clicks=True)
        rec.get_own_hwnd = lambda: 999
        rec._is_own_window = MagicMock(return_value=True)

        rec._on_click(400, 600, FakeButton("left"), True)
        rec._on_click(400, 600, FakeButton("left"), False)

        assert len(events) == 0

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_press_outside_release_on_own_window_emits_event(self, _mock_color):
        """Drags that START outside own window are captured even if they
        END on the own window (release is not filtered)."""
        rec, events = _make_recording_recorder(ignore_own_clicks=True)
        rec.get_own_hwnd = lambda: 999
        # Only return True for the press check at (400, 600)
        rec._is_own_window = MagicMock(side_effect=lambda x, y: x == 400)

        # Press at (100, 100) -- outside own window
        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(400, 600)
        # Release at (400, 600) -- on own window (but release isn't filtered)
        rec._on_click(400, 600, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.DRAG
        assert (events[0].x2, events[0].y2) == (400, 600)


# ---------------------------------------------------------------------------
# Error resilience in _emit_event
# ---------------------------------------------------------------------------

class TestEmitEventErrorResilience:
    """If _apply_window_context raises, the event should still be emitted
    with its original coordinates (not silently dropped)."""

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_window_context_error_still_emits_event(self, _mock_color):
        rec, events = _make_recording_recorder(coord_mode="Window")

        # Make _apply_window_context raise
        rec._apply_window_context = MagicMock(
            side_effect=RuntimeError("ctypes failure"),
        )

        rec._on_click(100, 200, FakeButton("left"), True)
        rec._on_click(100, 200, FakeButton("left"), False)

        assert len(events) == 1
        # Coordinates should be unchanged (screen coords, since conversion failed)
        assert events[0].x1 == 100
        assert events[0].y1 == 200

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_drag_survives_window_context_error(self, _mock_color):
        """Drag events survive _apply_window_context failures."""
        rec, events = _make_recording_recorder(coord_mode="Window")
        rec._apply_window_context = MagicMock(
            side_effect=OSError("EnumWindows failed"),
        )

        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_move(300, 300)
        rec._on_click(300, 300, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.DRAG
        assert (events[0].x1, events[0].y1) == (100, 100)
        assert (events[0].x2, events[0].y2) == (300, 300)


# ---------------------------------------------------------------------------
# Callback exception safety -- callbacks must not kill the pynput listener
# ---------------------------------------------------------------------------

class TestCallbackExceptionSafety:
    """Even if internal helpers raise, the callbacks should not propagate
    the exception (which would kill the pynput listener thread)."""

    def test_on_click_survives_get_pixel_color_error(self):
        rec, events = _make_recording_recorder()

        with patch("src.recorder.get_pixel_color", side_effect=Exception("GDI fail")):
            # Should not raise
            rec._on_click(100, 100, FakeButton("left"), True)
            rec._on_click(100, 100, FakeButton("left"), False)

        # No event emitted because the press failed, but no crash either
        assert len(events) == 0

    def test_on_move_survives_internal_error(self):
        rec, events = _make_recording_recorder()
        # Corrupt _press_info to trigger an error during iteration
        rec._press_info[MouseButton.LEFT] = "not a tuple"

        # Should not raise
        rec._on_move(200, 200)

    def test_on_key_press_survives_error(self):
        rec, events = _make_recording_recorder()

        # Pass an object that causes repr() to fail
        class BadKey:
            @property
            def char(self):
                raise RuntimeError("broken key")
            def __str__(self):
                raise RuntimeError("broken str")
            def __repr__(self):
                raise RuntimeError("broken repr")

        # Should not raise
        rec._on_key_press(BadKey())


# ---------------------------------------------------------------------------
# Stop recording hotkey (F9)
# ---------------------------------------------------------------------------

class TestStopHotkey:
    """F9 should trigger the on_stop_hotkey callback and NOT be recorded
    as a keystroke event."""

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_stop_hotkey_triggers_callback(self, _mock_color):
        stop_called = []
        rec, events = _make_recording_recorder(
            on_stop_hotkey=lambda: stop_called.append(True),
        )
        # Set up a fake stop key
        sentinel = object()
        rec._stop_key = sentinel

        rec._on_key_press(sentinel)

        assert len(stop_called) == 1
        assert len(events) == 0  # NOT recorded as keystroke

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_non_hotkey_recorded_as_keystroke(self, _mock_color):
        stop_called = []
        rec, events = _make_recording_recorder(
            on_stop_hotkey=lambda: stop_called.append(True),
        )
        sentinel = object()
        rec._stop_key = sentinel

        # Press a different key
        class FakeChar:
            char = "a"
        rec._on_key_press(FakeChar())

        assert len(stop_called) == 0
        assert len(events) == 1
        assert events[0].event_type == EventType.KEYSTROKE

    def test_stop_hotkey_no_callback_still_suppresses_keystroke(self):
        """Even with no callback, the hotkey press is suppressed."""
        rec, events = _make_recording_recorder(on_stop_hotkey=None)
        sentinel = object()
        rec._stop_key = sentinel

        rec._on_key_press(sentinel)
        assert len(events) == 0


# ---------------------------------------------------------------------------
# Session event accumulation
# ---------------------------------------------------------------------------

class TestSessionAccumulation:
    """Recorded events should accumulate in the current session."""

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_events_added_to_session(self, _mock_color):
        rec, events = _make_recording_recorder()

        rec._on_click(100, 100, FakeButton("left"), True)
        rec._on_click(100, 100, FakeButton("left"), False)
        rec._on_click(200, 200, FakeButton("left"), True)
        rec._on_move(300, 300)
        rec._on_click(300, 300, FakeButton("left"), False)

        session = rec._current_session
        assert len(session.events) == 2
        assert session.events[0].event_type == EventType.CLICK
        assert session.events[1].event_type == EventType.DRAG


# ---------------------------------------------------------------------------
# Android emulator use-case scenarios
# ---------------------------------------------------------------------------

class TestEmulatorScenarios:
    """Regression tests modelling typical Android emulator game automation
    workflows -- the primary use case for this tool."""

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_rapid_tap_sequence(self, _mock_color):
        """Multiple quick taps at different positions (menu navigation)."""
        rec, events = _make_recording_recorder()

        for x, y in [(100, 200), (300, 400), (500, 600)]:
            rec._on_click(x, y, FakeButton("left"), True)
            rec._on_click(x, y, FakeButton("left"), False)

        assert len(events) == 3
        assert all(e.event_type == EventType.CLICK for e in events)
        coords = [(e.x1, e.y1) for e in events]
        assert coords == [(100, 200), (300, 400), (500, 600)]

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_swipe_gesture(self, _mock_color):
        """Swipe gesture (long drag across the screen)."""
        rec, events = _make_recording_recorder()

        rec._on_click(50, 500, FakeButton("left"), True)
        # Simulate many intermediate move events (like a real swipe)
        for x in range(100, 800, 50):
            rec._on_move(x, 500)
        rec._on_click(800, 500, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.DRAG
        assert (events[0].x1, events[0].y1) == (50, 500)
        assert (events[0].x2, events[0].y2) == (800, 500)

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_tap_then_swipe(self, _mock_color):
        """Tap a button, then swipe (mixed click + drag sequence)."""
        rec, events = _make_recording_recorder()

        # Tap
        rec._on_click(300, 200, FakeButton("left"), True)
        rec._on_click(300, 200, FakeButton("left"), False)

        # Swipe
        rec._on_click(100, 400, FakeButton("left"), True)
        rec._on_move(600, 400)
        rec._on_click(600, 400, FakeButton("left"), False)

        assert len(events) == 2
        assert events[0].event_type == EventType.CLICK
        assert events[1].event_type == EventType.DRAG

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_long_press_no_move_is_click(self, _mock_color):
        """Long press without movement is a click (games use hold gestures
        but the recorder only distinguishes via movement, not time)."""
        rec, events = _make_recording_recorder()

        rec._on_click(400, 400, FakeButton("left"), True)
        # No movement events between press and release
        rec._on_click(400, 400, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.CLICK

    @patch("src.recorder.get_pixel_color", return_value="0x000000")
    def test_micro_jitter_during_tap_stays_click(self, _mock_color):
        """Small sub-pixel jitter during a tap should not turn it into a drag.
        Real mouse hardware often reports tiny movements during a click."""
        rec, events = _make_recording_recorder()

        rec._on_click(400, 400, FakeButton("left"), True)
        rec._on_move(401, 400)  # 1px jitter
        rec._on_move(400, 401)  # 1px jitter
        rec._on_move(401, 401)  # ~1.4px from origin
        rec._on_click(401, 401, FakeButton("left"), False)

        assert len(events) == 1
        assert events[0].event_type == EventType.CLICK
