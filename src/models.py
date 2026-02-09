"""Data models for the AHK Macro Builder."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class EventType(Enum):
    CLICK = "Click"
    DRAG = "Drag"
    MOVE = "Move"
    KEYSTROKE = "Key"


class MouseButton(Enum):
    LEFT = "Left"
    RIGHT = "Right"
    MIDDLE = "Middle"


class CoordMode(Enum):
    SCREEN = "Screen"
    WINDOW = "Window"
    CLIENT = "Client"


class RecordingState(Enum):
    IDLE = "Idle"
    RECORDING = "Recording"
    PAUSED = "Paused"


@dataclass
class RecordedEvent:
    """A single recorded mouse event."""
    timestamp: float
    event_type: EventType
    button: MouseButton
    x1: int
    y1: int
    x2: Optional[int] = None
    y2: Optional[int] = None
    color1: Optional[str] = None  # hex color e.g. "0xRRGGBB"
    color2: Optional[str] = None  # hex color for drag end point
    key_text: Optional[str] = None  # for KEYSTROKE events
    modifiers: list = field(default_factory=list)

    def description(self) -> str:
        """Human-readable description of this event."""
        if self.event_type == EventType.CLICK:
            color_str = f" color={self.color1}" if self.color1 else ""
            return f"{self.button.value} Click at ({self.x1}, {self.y1}){color_str}"
        elif self.event_type == EventType.DRAG:
            return (
                f"{self.button.value} Drag from ({self.x1}, {self.y1}) "
                f"to ({self.x2}, {self.y2})"
            )
        elif self.event_type == EventType.MOVE:
            return f"Move to ({self.x1}, {self.y1})"
        elif self.event_type == EventType.KEYSTROKE:
            return f"Key: {self.key_text or '?'}"
        return "Unknown event"


@dataclass
class Session:
    """A recording session containing a sequence of events."""
    id: int
    name: str
    created_at: float = field(default_factory=time.time)
    events: list = field(default_factory=list)
    coord_mode: CoordMode = CoordMode.SCREEN

    def add_event(self, event: RecordedEvent):
        self.events.append(event)
