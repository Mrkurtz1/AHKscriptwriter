"""AHK v2 code generator from recorded sessions."""

from typing import List, Optional

from src.models import (
    CoordMode,
    EventType,
    MouseButton,
    RecordedEvent,
    Session,
)
from src.settings import AppSettings

# Keys that need to be wrapped in braces for AHK v2 Send
_AHK_SPECIAL_KEYS = {
    "Key.space": " ",
    "Key.enter": "{Enter}",
    "Key.tab": "{Tab}",
    "Key.backspace": "{Backspace}",
    "Key.delete": "{Delete}",
    "Key.esc": "{Escape}",
    "Key.up": "{Up}",
    "Key.down": "{Down}",
    "Key.left": "{Left}",
    "Key.right": "{Right}",
    "Key.home": "{Home}",
    "Key.end": "{End}",
    "Key.page_up": "{PgUp}",
    "Key.page_down": "{PgDn}",
    "Key.insert": "{Insert}",
    "Key.f1": "{F1}",
    "Key.f2": "{F2}",
    "Key.f3": "{F3}",
    "Key.f4": "{F4}",
    "Key.f5": "{F5}",
    "Key.f6": "{F6}",
    "Key.f7": "{F7}",
    "Key.f8": "{F8}",
    "Key.f9": "{F9}",
    "Key.f10": "{F10}",
    "Key.f11": "{F11}",
    "Key.f12": "{F12}",
}


class CodeGenerator:
    """Generates valid AutoHotkey v2 code from recorded events."""

    def __init__(self, settings: AppSettings):
        self.settings = settings

    def generate_header(self, coord_mode: CoordMode, target_window: str = "") -> str:
        """Generate the AHK v2 script header with CoordMode and directives."""
        lines = [
            "#Requires AutoHotkey v2.0",
            f'CoordMode "Mouse", "{coord_mode.value}"',
            f'CoordMode "Pixel", "{coord_mode.value}"',
            'SetDefaultMouseSpeed 0',
        ]

        if coord_mode in (CoordMode.WINDOW, CoordMode.CLIENT):
            title = target_window or self.settings.target_window_title
            lines.append("")
            lines.append(f"; Coordinate mode: \"{coord_mode.value}\" - coordinates are relative to the target window.")
            lines.append("; WinActivate is called at the start of each macro to focus the correct window.")
            if title:
                lines.append(f'; Target window: "{title}"')

        lines.append("")
        return "\n".join(lines)

    def generate_event_line(self, event: RecordedEvent, speed_mult: float = 1.0) -> str:
        """Generate an AHK v2 code line for a single event."""
        if event.event_type == EventType.CLICK:
            return self._generate_click(event)
        elif event.event_type == EventType.DRAG:
            return self._generate_drag(event, speed_mult)
        elif event.event_type == EventType.MOVE:
            return self._generate_move(event)
        elif event.event_type == EventType.KEYSTROKE:
            return self._generate_keystroke(event)
        return f"    ; Unknown event type: {event.event_type}"

    def _generate_click(self, event: RecordedEvent) -> str:
        """Generate a Click statement with color comment."""
        button_str = self._button_str(event.button)
        color_comment = ""
        if event.color1:
            color_comment = f"  ; color={event.color1} at record time"

        if event.button == MouseButton.LEFT:
            return f"    Click {event.x1}, {event.y1}{color_comment}"
        else:
            return f'    Click "{button_str}", {event.x1}, {event.y1}{color_comment}'

    def _generate_drag(self, event: RecordedEvent, speed_mult: float = 1.0) -> str:
        """Generate drag code (MouseClickDrag) with color comments."""
        button_str = self._button_str(event.button)
        lines = []

        color1_comment = ""
        if event.color1:
            color1_comment = f"  ; start color={event.color1}"

        lines.append(
            f'    MouseClickDrag "{button_str}", '
            f"{event.x1}, {event.y1}, {event.x2}, {event.y2}"
            f"{color1_comment}"
        )

        if event.color2:
            lines.append(f"    ; end color={event.color2}")

        return "\n".join(lines)

    def _generate_move(self, event: RecordedEvent) -> str:
        """Generate a MouseMove statement."""
        return f"    MouseMove {event.x1}, {event.y1}"

    def _generate_keystroke(self, event: RecordedEvent) -> str:
        """Generate a Send statement for a keystroke."""
        key = event.key_text or ""
        ahk_key = _AHK_SPECIAL_KEYS.get(key)
        if ahk_key is not None:
            return f'    Send "{ahk_key}"'
        # For printable characters, Send the character directly
        # Strip quotes from pynput char representation like "'a'"
        char = key.strip("'")
        if len(char) == 1:
            # Escape AHK special chars in Send: { } ! ^ + #
            if char in "{}!^+#":
                return f'    Send "{{{char}}}"'
            return f'    Send "{char}"'
        return f"    ; Unrecognized key: {key}"

    def _button_str(self, button: MouseButton) -> str:
        return button.value

    def generate_subroutine(
        self,
        session: Session,
        events: Optional[List[RecordedEvent]] = None,
    ) -> str:
        """Generate a complete AHK v2 function for a session."""
        if events is None:
            events = session.events

        lines = [f"{session.name}() {{"]

        # In Window/Client mode, add WinActivate at the start of each subroutine
        if session.coord_mode in (CoordMode.WINDOW, CoordMode.CLIENT):
            # Use per-session captured title, fall back to global settings
            title = session.target_window_title or self.settings.target_window_title
            if title:
                lines.append(f'    ; Window-relative mode: activating "{title}"')
                lines.append(f'    WinActivate "{title}"')
                lines.append(f'    WinWaitActive "{title}",, 5  ; wait up to 5s for window')
            else:
                lines.append("    ; WARNING: No target window title was detected or configured.")
                lines.append("    ; Set a target window title in Settings, or ensure the target")
                lines.append("    ; window is in the foreground when you start recording.")
                lines.append('    ; WinActivate "YourWindowTitle"')

        if not events:
            lines.append("    ; No events recorded")
        else:
            prev_time = None
            for event in events:
                # Insert Sleep between events based on time gaps
                if prev_time is not None:
                    gap_ms = int((event.timestamp - prev_time) * 1000)
                    gap_ms = int(gap_ms * self.settings.replay_speed_multiplier)
                    if gap_ms > 50:
                        lines.append(f"    Sleep {gap_ms}")
                lines.append(self.generate_event_line(event))
                prev_time = event.timestamp

        lines.append("}")
        return "\n".join(lines)

    def generate_full_script(self, sessions: List[Session]) -> str:
        """Generate a complete AHK v2 script from multiple sessions."""
        if not sessions:
            return self.generate_header(self.settings.get_coord_mode())

        coord_mode = sessions[0].coord_mode
        target_window = sessions[0].target_window_title
        parts = [self.generate_header(coord_mode, target_window=target_window)]

        for session in sessions:
            parts.append(self.generate_subroutine(session))
            parts.append("")  # blank line between subroutines

        # Add call to last macro for convenience
        if sessions:
            last = sessions[-1]
            parts.append(f"; Call the last recorded macro:")
            parts.append(f"; {last.name}()")

        return "\n".join(parts)

    def append_subroutine_to_script(
        self, existing_script: str, session: Session
    ) -> str:
        """Append a new subroutine to an existing script."""
        subroutine = self.generate_subroutine(session)

        if not existing_script.strip():
            header = self.generate_header(
                session.coord_mode, target_window=session.target_window_title
            )
            return f"{header}\n{subroutine}\n"

        return f"{existing_script}\n\n{subroutine}\n"
