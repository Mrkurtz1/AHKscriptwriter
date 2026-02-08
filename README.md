# AHK Macro Builder

A Windows desktop application that records mouse interactions and generates AutoHotkey v2 code for replaying macros, primarily aimed at automating actions in Android emulator games.

## Features

- **Record mouse clicks and drags** with automatic pixel color annotation
- **Generate valid AHK v2 code** with proper `CoordMode`, `Click`, and `MouseClickDrag` statements
- **Live Code Window** showing generated script with syntax editing, undo/redo, and find
- **Replay** scripts directly through AutoHotkey v2 runtime
- **Drag detection** distinguishes clicks from drags using configurable pixel threshold
- **Coordinate modes** supporting Screen, Window, and Client modes
- **Session-based recording** creating a new subroutine per recording session
- **Configurable settings** including drag threshold, movement recording, replay speed

## Requirements

- Python 3.9+
- Windows 10/11
- AutoHotkey v2 (for replay functionality)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python run.py
```

### Workflow

1. Launch the application
2. Configure coordinate mode and settings as needed
3. Click **Start** to begin recording
4. Perform mouse clicks and drags in your emulator window
5. Click **Stop** to end recording
6. Review the generated AHK v2 code in the Code Window
7. Edit the code if needed
8. Click **Replay** to execute the script via AutoHotkey

## Project Structure

```
├── run.py                      # Application launcher
├── requirements.txt            # Python dependencies
└── src/
    ├── main.py                 # Entry point
    ├── app.py                  # Main application window
    ├── models.py               # Data models (Event, Session, enums)
    ├── settings.py             # Settings management (JSON config)
    ├── recorder.py             # Mouse event recorder with drag detection
    ├── code_generator.py       # AHK v2 code generator
    ├── replay.py               # Script execution via AutoHotkey.exe
    └── ui/
        ├── toolbar.py          # Recording and replay controls
        ├── event_log.py        # Human-readable event log panel
        ├── code_window.py      # Code editor with find/save/load
        ├── status_bar.py       # Status bar with state indicators
        └── settings_dialog.py  # Settings configuration dialog
```

## Generated Code Example

```ahk
#Requires AutoHotkey v2.0
CoordMode "Mouse", "Screen"
CoordMode "Pixel", "Screen"
SetDefaultMouseSpeed 0

Macro_20260208_143022() {
    Click 500, 300  ; color=0xFF0000 at record time
    Sleep 1200
    Click 600, 400  ; color=0x00FF00 at record time
    Sleep 800
    MouseClickDrag "Left", 100, 200, 400, 500  ; start color=0x0000FF
    ; end color=0xFFFFFF
}
```

## License

MIT
