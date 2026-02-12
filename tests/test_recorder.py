"""Tests for recorder.py -- coordinate conversion and window context edge cases.

Since the Windows ctypes APIs are unavailable on Linux, we mock the
platform-specific helpers and test the Recorder logic directly.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.models import EventType, MouseButton, RecordedEvent, CoordMode
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
