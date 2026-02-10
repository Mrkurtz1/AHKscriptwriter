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
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_click_coords_converted(self, mock_wuc, mock_fg, mock_root,
                                     mock_convert, mock_title):
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        mock_convert.assert_called_once_with(12345, 500, 600)
        assert event.x1 == 100
        assert event.y1 == 150
        assert event.window_title == "Notepad"

    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_window", side_effect=[(10, 20), (110, 220)])
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_drag_both_coords_converted(self, mock_wuc, mock_fg, mock_root,
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
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_client_mode_uses_screen_to_client(self, mock_wuc, mock_fg,
                                                mock_root, mock_convert,
                                                mock_title):
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
    @patch("src.recorder._get_foreground_hwnd", return_value=999)
    @patch("src.recorder._get_window_under_cursor", return_value=999)
    def test_own_window_hwnd_skips_conversion(self, mock_wuc, mock_fg,
                                               mock_root, mock_title):
        """When the target HWND is our own window, skip title and conversion."""
        rec = _make_recorder(coord_mode="Window")
        # _is_own_hwnd checks GetAncestor which we need to mock
        rec._is_own_hwnd = MagicMock(return_value=True)
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        assert event.x1 == 500  # unchanged
        assert event.y1 == 600
        assert event.window_title is None


# ---------------------------------------------------------------------------
# Zero HWND fallback
# ---------------------------------------------------------------------------

class TestZeroHwndFallback:
    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=0)
    def test_zero_cursor_hwnd_falls_back_to_foreground(self, mock_wuc, mock_fg,
                                                        mock_root, mock_convert,
                                                        mock_title):
        """If WindowFromPoint returns 0, fall back to GetForegroundWindow."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        # Should have called GetForegroundWindow as fallback
        assert mock_fg.call_count >= 1
        # Conversion should still happen
        assert event.x1 == 50
        assert event.y1 == 50

    @patch("src.recorder._get_root_hwnd", return_value=0)
    @patch("src.recorder._get_foreground_hwnd", return_value=0)
    @patch("src.recorder._get_window_under_cursor", return_value=0)
    def test_all_zero_hwnd_skips_everything(self, mock_wuc, mock_fg, mock_root):
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
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_first_event_sets_target(self, mock_wuc, mock_fg, mock_root,
                                      mock_convert, mock_title):
        rec = _make_recorder(coord_mode="Window", target_title="")
        event = _make_event()

        rec._apply_window_context(event)

        assert rec.settings.target_window_title == "FirstWindow"

    @patch("src.recorder._get_window_title", return_value="SecondWindow")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_existing_target_not_overwritten(self, mock_wuc, mock_fg, mock_root,
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
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_empty_title_still_converts_coords(self, mock_wuc, mock_fg,
                                                mock_root, mock_convert,
                                                mock_title):
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
    @patch("src.recorder._get_window_under_cursor", return_value=99999)
    def test_keystroke_prefers_foreground(self, mock_wuc, mock_fg, mock_root,
                                          mock_convert, mock_title):
        """Keystroke events should use GetForegroundWindow, not WindowFromPoint."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(event_type=EventType.KEYSTROKE, key_text="'a'")

        rec._apply_window_context(event)

        # Should have called foreground directly, not window_under_cursor
        mock_fg.assert_called()
        assert event.window_title == "Editor"
