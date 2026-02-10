"""Tests for code_generator.py -- window switching and coordinate edge cases."""

import pytest

from src.models import CoordMode, EventType, MouseButton, RecordedEvent, Session
from src.settings import AppSettings
from src.code_generator import CodeGenerator, _escape_ahk_title


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type=EventType.CLICK,
    button=MouseButton.LEFT,
    x1=100, y1=200,
    x2=None, y2=None,
    window_title=None,
    key_text=None,
    ts=1000.0,
):
    return RecordedEvent(
        timestamp=ts,
        event_type=event_type,
        button=button,
        x1=x1, y1=y1,
        x2=x2, y2=y2,
        window_title=window_title,
        key_text=key_text,
    )


def _make_session(events, coord_mode=CoordMode.WINDOW, name="TestMacro"):
    s = Session(id=1, name=name, coord_mode=coord_mode)
    for e in events:
        s.add_event(e)
    return s


# ---------------------------------------------------------------------------
# _escape_ahk_title
# ---------------------------------------------------------------------------

class TestEscapeAhkTitle:
    def test_no_quotes(self):
        assert _escape_ahk_title("Notepad") == "Notepad"

    def test_double_quotes_escaped(self):
        assert _escape_ahk_title('My "App" Name') == 'My `"App`" Name'

    def test_empty_string(self):
        assert _escape_ahk_title("") == ""

    def test_only_quotes(self):
        assert _escape_ahk_title('""') == '`"`"'


# ---------------------------------------------------------------------------
# Multi-window WinActivate generation
# ---------------------------------------------------------------------------

class TestMultiWindowActivation:
    def test_single_window_one_winactivate(self):
        """All events on the same window should produce exactly one WinActivate."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title="Notepad", ts=2.0),
            _make_event(window_title="Notepad", ts=3.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        assert code.count('WinActivate "Notepad"') == 1
        assert code.count('WinWaitActive "Notepad"') == 1

    def test_two_windows_switch(self):
        """Switching from window A to B should produce two WinActivate blocks."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title="Calculator", ts=2.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        assert code.count('WinActivate "Notepad"') == 1
        assert code.count('WinActivate "Calculator"') == 1

    def test_switch_back_to_original_window(self):
        """A -> B -> A should produce three WinActivate blocks."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title="Calculator", ts=2.0),
            _make_event(window_title="Notepad", ts=3.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        # Notepad should appear twice (once initially, once when switching back)
        assert code.count('WinActivate "Notepad"') == 2
        assert code.count('WinActivate "Calculator"') == 1

    def test_three_windows_interleaved(self):
        """A -> B -> C -> A should produce four WinActivate blocks."""
        events = [
            _make_event(window_title="App1", ts=1.0),
            _make_event(window_title="App2", ts=2.0),
            _make_event(window_title="App3", ts=3.0),
            _make_event(window_title="App1", ts=4.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        assert code.count("WinActivate") == 4  # each includes WinWaitActive too
        # WinActivate + WinWaitActive = 2 lines per switch, 4 switches = 8 lines
        # But count just the WinActivate (not WinWaitActive)
        lines = code.splitlines()
        activate_lines = [l for l in lines if l.strip().startswith('WinActivate')]
        assert len(activate_lines) == 4


# ---------------------------------------------------------------------------
# Missing window title handling
# ---------------------------------------------------------------------------

class TestMissingWindowTitle:
    def test_event_without_title_inherits_last(self):
        """An event without window_title should NOT trigger a new WinActivate."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title=None, ts=2.0),  # title not captured
            _make_event(window_title="Notepad", ts=3.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        # Only one WinActivate since title didn't actually change
        assert code.count('WinActivate "Notepad"') == 1

    def test_missing_title_then_new_window(self):
        """Missing title followed by a different window should WinActivate the new one."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title=None, ts=2.0),
            _make_event(window_title="Calculator", ts=3.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        assert code.count('WinActivate "Notepad"') == 1
        assert code.count('WinActivate "Calculator"') == 1

    def test_no_titles_at_all_uses_settings_target(self):
        """When no event has a title, fall back to settings target_window_title."""
        events = [
            _make_event(window_title=None, ts=1.0),
            _make_event(window_title=None, ts=2.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(
            coord_mode="Window",
            target_window_title="FallbackApp",
        ))
        code = gen.generate_subroutine(session)

        assert 'WinActivate "FallbackApp"' in code

    def test_no_titles_no_target_shows_comment(self):
        """When nothing is available, a helpful comment should appear."""
        events = [
            _make_event(window_title=None, ts=1.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window", target_window_title=""))
        code = gen.generate_subroutine(session)

        assert "Set a target window title" in code


# ---------------------------------------------------------------------------
# Title escaping in generated code
# ---------------------------------------------------------------------------

class TestTitleEscapingInGeneration:
    def test_quotes_in_title_escaped(self):
        """Window title with quotes should be escaped with backtick."""
        events = [
            _make_event(window_title='My "App" v2', ts=1.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        assert 'WinActivate "My `"App`" v2"' in code
        assert 'WinWaitActive "My `"App`" v2"' in code


# ---------------------------------------------------------------------------
# Screen mode: no WinActivate at all
# ---------------------------------------------------------------------------

class TestScreenMode:
    def test_screen_mode_no_winactivate(self):
        """Screen coordinate mode should never emit WinActivate."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
            _make_event(window_title="Calculator", ts=2.0),
        ]
        session = _make_session(events, coord_mode=CoordMode.SCREEN)
        gen = CodeGenerator(AppSettings(coord_mode="Screen"))
        code = gen.generate_subroutine(session)

        assert "WinActivate" not in code


# ---------------------------------------------------------------------------
# Client mode behaves like Window mode for WinActivate
# ---------------------------------------------------------------------------

class TestClientMode:
    def test_client_mode_emits_winactivate(self):
        """Client coordinate mode should also emit WinActivate."""
        events = [
            _make_event(window_title="Notepad", ts=1.0),
        ]
        session = _make_session(events, coord_mode=CoordMode.CLIENT)
        gen = CodeGenerator(AppSettings(coord_mode="Client"))
        code = gen.generate_subroutine(session)

        assert 'WinActivate "Notepad"' in code


# ---------------------------------------------------------------------------
# Coordinates appear correctly in generated code
# ---------------------------------------------------------------------------

class TestCoordinateOutput:
    def test_click_coordinates_in_output(self):
        """Verify the coordinates from the event appear in the Click command."""
        events = [
            _make_event(x1=50, y1=75, window_title="App", ts=1.0),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        assert "Click 50, 75" in code

    def test_drag_coordinates_in_output(self):
        """Verify drag start and end coordinates appear in MouseClickDrag."""
        events = [
            _make_event(
                event_type=EventType.DRAG,
                x1=10, y1=20, x2=110, y2=220,
                window_title="App", ts=1.0,
            ),
        ]
        session = _make_session(events)
        gen = CodeGenerator(AppSettings(coord_mode="Window"))
        code = gen.generate_subroutine(session)

        assert "10, 20, 110, 220" in code
