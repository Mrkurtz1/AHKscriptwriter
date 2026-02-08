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


class CodeGenerator:
    """Generates valid AutoHotkey v2 code from recorded events."""

    def __init__(self, settings: AppSettings):
        self.settings = settings

    def generate_header(self, coord_mode: CoordMode) -> str:
        """Generate the AHK v2 script header with CoordMode and directives."""
        lines = [
            "#Requires AutoHotkey v2.0",
            f'CoordMode "Mouse", "{coord_mode.value}"',
            f'CoordMode "Pixel", "{coord_mode.value}"',
            'SetDefaultMouseSpeed 0',
            "",
        ]
        return "\n".join(lines)

    def generate_event_line(self, event: RecordedEvent, speed_mult: float = 1.0) -> str:
        """Generate an AHK v2 code line for a single event."""
        if event.event_type == EventType.CLICK:
            return self._generate_click(event)
        elif event.event_type == EventType.DRAG:
            return self._generate_drag(event, speed_mult)
        elif event.event_type == EventType.MOVE:
            return self._generate_move(event)
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
        parts = [self.generate_header(coord_mode)]

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
            header = self.generate_header(session.coord_mode)
            return f"{header}\n{subroutine}\n"

        return f"{existing_script}\n\n{subroutine}\n"
