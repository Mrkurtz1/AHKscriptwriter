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

    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_window", return_value=(100, 150))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_click_coords_converted(self, mock_wuc, mock_fg, mock_root,
                                     mock_convert, mock_title, mock_contains):
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=500, y1=600)

        rec._apply_window_context(event)

        mock_convert.assert_called_once_with(12345, 500, 600)
        assert event.x1 == 100
        assert event.y1 == 150
        assert event.window_title == "Notepad"

    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_window", side_effect=[(10, 20), (110, 220)])
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_drag_both_coords_converted(self, mock_wuc, mock_fg, mock_root,
                                         mock_convert, mock_title, mock_contains):
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
    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_client", return_value=(80, 130))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_client_mode_uses_screen_to_client(self, mock_wuc, mock_fg,
                                                mock_root, mock_convert,
                                                mock_title, mock_contains):
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
    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="AHK Macro Builder")
    @patch("src.recorder._get_root_hwnd", return_value=999)
    @patch("src.recorder._get_foreground_hwnd", return_value=999)
    @patch("src.recorder._get_window_under_cursor", return_value=999)
    def test_own_window_hwnd_skips_conversion(self, mock_wuc, mock_fg,
                                               mock_root, mock_title,
                                               mock_contains):
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
    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="Notepad")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=0)
    def test_zero_cursor_hwnd_falls_back_to_foreground(self, mock_wuc, mock_fg,
                                                        mock_root, mock_convert,
                                                        mock_title, mock_contains):
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
    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="FirstWindow")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_first_event_sets_target(self, mock_wuc, mock_fg, mock_root,
                                      mock_convert, mock_title, mock_contains):
        rec = _make_recorder(coord_mode="Window", target_title="")
        event = _make_event()

        rec._apply_window_context(event)

        assert rec.settings.target_window_title == "FirstWindow"

    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="SecondWindow")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_existing_target_not_overwritten(self, mock_wuc, mock_fg, mock_root,
                                              mock_convert, mock_title,
                                              mock_contains):
        rec = _make_recorder(coord_mode="Window", target_title="AlreadySet")
        event = _make_event()

        rec._apply_window_context(event)

        assert rec.settings.target_window_title == "AlreadySet"


# ---------------------------------------------------------------------------
# Empty window title handling
# ---------------------------------------------------------------------------

class TestEmptyWindowTitle:
    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="")
    @patch("src.recorder._screen_to_window", return_value=(50, 50))
    @patch("src.recorder._get_root_hwnd", return_value=12345)
    @patch("src.recorder._get_foreground_hwnd", return_value=12345)
    @patch("src.recorder._get_window_under_cursor", return_value=12345)
    def test_empty_title_still_converts_coords(self, mock_wuc, mock_fg,
                                                mock_root, mock_convert,
                                                mock_title, mock_contains):
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


# ---------------------------------------------------------------------------
# Nested frame / owned-window resolution -- foreground-preferred path
# ---------------------------------------------------------------------------

class TestNestedFrameResolution:
    """When clicking inside a frame (owned sub-window), coordinates should
    be relative to the main application window, not the frame.

    The recorder now prefers the foreground window for mouse events when
    the click falls within its bounds, which bypasses the
    WindowFromPoint -> GetAncestor(GA_ROOTOWNER) chain entirely.
    """

    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="MainApp")
    @patch("src.recorder._screen_to_window", return_value=(200, 100))
    @patch("src.recorder._get_root_hwnd", return_value=1000)
    @patch("src.recorder._get_foreground_hwnd", return_value=1000)
    @patch("src.recorder._get_window_under_cursor", return_value=5555)
    def test_child_control_uses_foreground_window(self, mock_wuc, mock_fg,
                                                    mock_root, mock_convert,
                                                    mock_title, mock_contains):
        """WindowFromPoint returns a child control (5555), but the
        foreground window (1000) is used directly because the click
        falls within its bounds -- coordinates are relative to the
        main application window."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=700, y1=500)

        rec._apply_window_context(event)

        # Foreground window used; _get_root_hwnd called with fg HWND
        mock_root.assert_called_once_with(1000)
        # WindowFromPoint is NOT consulted (foreground path short-circuits)
        mock_wuc.assert_not_called()
        # Coordinates relative to foreground / root owner (1000)
        mock_convert.assert_called_once_with(1000, 700, 500)
        assert event.x1 == 200
        assert event.y1 == 100
        assert event.window_title == "MainApp"

    @patch("src.recorder._window_rect_contains", return_value=True)
    @patch("src.recorder._get_window_title", return_value="MainApp")
    @patch("src.recorder._screen_to_window", side_effect=[(200, 100), (400, 300)])
    @patch("src.recorder._get_root_hwnd", return_value=1000)
    @patch("src.recorder._get_foreground_hwnd", return_value=1000)
    @patch("src.recorder._get_window_under_cursor", return_value=5555)
    def test_drag_in_frame_uses_foreground_for_both_coords(
        self, mock_wuc, mock_fg, mock_root, mock_convert, mock_title,
        mock_contains,
    ):
        """Drag events inside a frame should convert both start and end
        coordinates relative to the main application (foreground) window."""
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
# Fallback to WindowFromPoint when click is outside the foreground window
# ---------------------------------------------------------------------------

class TestFallbackToWindowFromPoint:
    """When the click point falls outside the foreground window's rect,
    the recorder should fall back to the WindowFromPoint approach."""

    @patch("src.recorder._window_rect_contains", return_value=False)
    @patch("src.recorder._get_window_title", return_value="OtherApp")
    @patch("src.recorder._screen_to_window", return_value=(30, 40))
    @patch("src.recorder._get_root_hwnd", side_effect=lambda h: {2000: 2000, 3000: 3000}.get(h, h))
    @patch("src.recorder._get_foreground_hwnd", return_value=2000)
    @patch("src.recorder._get_window_under_cursor", return_value=3000)
    def test_click_outside_fg_uses_window_from_point(
        self, mock_wuc, mock_fg, mock_root, mock_convert, mock_title,
        mock_contains,
    ):
        """Click outside the foreground window should use WindowFromPoint."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=1500, y1=800)

        rec._apply_window_context(event)

        # _window_rect_contains returned False for foreground, so
        # WindowFromPoint is used instead.
        mock_wuc.assert_called_once_with(1500, 800)
        # _get_root_hwnd is called for the fg check and then for the
        # WindowFromPoint result.
        assert mock_root.call_count == 2
        # Coordinates converted relative to the WindowFromPoint root (3000)
        mock_convert.assert_called_once_with(3000, 1500, 800)
        assert event.x1 == 30
        assert event.y1 == 40

    @patch("src.recorder._window_rect_contains", return_value=False)
    @patch("src.recorder._get_window_title", return_value="FallbackApp")
    @patch("src.recorder._screen_to_window", return_value=(10, 20))
    @patch("src.recorder._get_root_hwnd", side_effect=lambda h: {2000: 2000, 0: 0, 4000: 4000}.get(h, h))
    @patch("src.recorder._get_foreground_hwnd", return_value=2000)
    @patch("src.recorder._get_window_under_cursor", return_value=0)
    def test_click_outside_fg_and_wuc_zero_falls_back_to_fg(
        self, mock_wuc, mock_fg, mock_root, mock_convert, mock_title,
        mock_contains,
    ):
        """If click is outside fg rect AND WindowFromPoint returns 0,
        fall back to GetForegroundWindow for the conversion."""
        rec = _make_recorder(coord_mode="Window")
        event = _make_event(x1=1500, y1=800)

        rec._apply_window_context(event)

        # WindowFromPoint returned 0, so we fall back to foreground
        assert mock_fg.call_count >= 2  # once for fg check, once for fallback
        mock_convert.assert_called_once_with(2000, 1500, 800)
        assert event.x1 == 10
        assert event.y1 == 20
