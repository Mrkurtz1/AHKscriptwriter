"""Tests for event log window activation entries and coordinate display."""

import pytest
from unittest.mock import MagicMock, patch, call

from src.models import EventType, MouseButton, RecordedEvent, CoordMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type=EventType.CLICK,
    x1=100, y1=200,
    x2=None, y2=None,
    window_title=None,
    color1=None,
    key_text=None,
    ts=1000.0,
):
    return RecordedEvent(
        timestamp=ts,
        event_type=event_type,
        button=MouseButton.LEFT,
        x1=x1, y1=y1,
        x2=x2, y2=y2,
        window_title=window_title,
        color1=color1,
        key_text=key_text,
    )


# ---------------------------------------------------------------------------
# Window activation tracking logic (mirrors app._handle_recorded_event)
# ---------------------------------------------------------------------------

class TestWindowActivationTracking:
    """Test the window activation detection logic used by the app layer."""

    def _simulate_handle_events(self, events):
        """Simulate _handle_recorded_event logic, returning activation titles."""
        last_title = None
        activations = []
        for event in events:
            if event.window_title and event.window_title != last_title:
                activations.append(event.window_title)
                last_title = event.window_title
        return activations

    def test_single_window_one_activation(self):
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title="Notepad", ts=2.0),
            _make_event(window_title="Notepad", ts=3.0),
        ]
        activations = self._simulate_handle_events(events)
        assert activations == ["Notepad"]

    def test_two_windows_two_activations(self):
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title="Calculator", ts=2.0),
        ]
        activations = self._simulate_handle_events(events)
        assert activations == ["Notepad", "Calculator"]

    def test_switch_back_three_activations(self):
        """A -> B -> A produces three activation entries."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title="Calculator", ts=2.0),
            _make_event(window_title="Notepad", ts=3.0),
        ]
        activations = self._simulate_handle_events(events)
        assert activations == ["Notepad", "Calculator", "Notepad"]

    def test_none_title_no_activation(self):
        """Events without window_title should not produce activation entries."""
        events = [
            _make_event(window_title=None, ts=1.0),
            _make_event(window_title=None, ts=2.0),
        ]
        activations = self._simulate_handle_events(events)
        assert activations == []

    def test_none_title_between_same_window(self):
        """A None title between same windows should not cause extra activation."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title=None, ts=2.0),
            _make_event(window_title="Notepad", ts=3.0),
        ]
        activations = self._simulate_handle_events(events)
        # "Notepad" appears twice because after None, last_title is still
        # "Notepad", so the third event doesn't trigger a new activation
        assert activations == ["Notepad"]

    def test_none_title_then_new_window(self):
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title=None, ts=2.0),
            _make_event(window_title="Calculator", ts=3.0),
        ]
        activations = self._simulate_handle_events(events)
        assert activations == ["Notepad", "Calculator"]

    def test_reset_between_sessions(self):
        """Resetting last_title (like starting a new recording) should
        cause the first window to appear as a new activation again."""
        events_session1 = [
            _make_event(window_title="Notepad", ts=1.0),
        ]
        events_session2 = [
            _make_event(window_title="Notepad", ts=10.0),
        ]

        # Session 1
        activations1 = self._simulate_handle_events(events_session1)
        assert activations1 == ["Notepad"]

        # Session 2 (reset simulated by starting fresh)
        activations2 = self._simulate_handle_events(events_session2)
        assert activations2 == ["Notepad"]


# ---------------------------------------------------------------------------
# Event descriptions show correct coordinates
# ---------------------------------------------------------------------------

class TestEventDescriptionCoordinates:
    """Verify that event descriptions use the coordinates stored on the event
    (which are already window-relative after recorder conversion)."""

    def test_click_shows_converted_coords(self):
        event = _make_event(x1=100, y1=150, color1="0xFF0000")
        desc = event.description()
        assert "(100, 150)" in desc

    def test_drag_shows_converted_coords(self):
        event = _make_event(
            event_type=EventType.DRAG,
            x1=10, y1=20, x2=110, y2=220,
        )
        desc = event.description()
        assert "(10, 20)" in desc
        assert "(110, 220)" in desc

    def test_move_shows_converted_coords(self):
        event = _make_event(event_type=EventType.MOVE, x1=50, y1=75)
        desc = event.description()
        assert "(50, 75)" in desc

    def test_keystroke_description(self):
        event = _make_event(
            event_type=EventType.KEYSTROKE,
            key_text="'a'",
        )
        desc = event.description()
        assert "'a'" in desc
