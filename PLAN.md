# ReachLab - Project Plan

## Overview
A virtual reaching game using Polhemus Liberty (up to 4 sensors) for position tracking.
Built with Python 3.12 + Pygame + pygame_gui.

---

## Tech Stack
- Python 3.12 (.venv312)
- Pygame 2.6.1 + pygame_gui 0.6.14
- Polhemus Liberty via named pipe: \\.\pipe\PDIPnOPipe

---

## Screen Flow
```
Main Menu  [Liberty Status: ● CONNECTED / ○ DISCONNECTED]
├── Space Calibration  → run new calibration OR load existing CSV → back
├── Digitization       → Mode 0/1/2/3 → back
├── Session Setting    → participant ID, session info → back
├── Target Setting     → target positions, size, count → back
├── Start              → Game Screen
└── Quit
```

---

## Space Calibration (workspace mapping)
- Corrects for Liberty field distortion across workspace (Y/Z axes)
- Based on grid measurement (calibrate.py) → CSV file
- Options in menu:
  - Run new calibration (launches calibrate.py flow)
  - Load existing CSV (file picker)
- Once set, stays fixed until source is physically moved
- Current file: CalibrationRelated/calibration_20260505_181600.csv

---

## Sensor Setup Modes

### Mode 0: Skip
- Sensor 1 raw position = right hand cursor
- Sensor 2 raw position = left hand cursor

### Mode 1: MCP only [IMPLEMENT FIRST]
Sensors: S1=right hand dorsum, S2=left hand dorsum, S3=pointer

Digitization:
- Press 1: pointer at right MCP → offset_local = R_s1⁻¹ × (P_s3 - P_s1)
- Press 2: pointer at left MCP  → offset_local = R_s2⁻¹ × (P_s3 - P_s2)

Tracking:
- Right MCP = P_s1 + R_s1 × offset_mcp_right
- Left MCP  = P_s2 + R_s2 × offset_mcp_left

### Mode 2: Wrist angle [FUTURE]
Sensors: S1=right hand, S2=left hand, S3=right forearm, S4=left forearm

Landmarks digitized:
- Each hand: MCP, wrist medial, wrist lateral → relative to hand sensor
- Each elbow: medial, lateral → relative to forearm sensor
  - Right arm: S3 acts as pointer first (steps 1-5), then attaches to forearm (step 6 finalizes)
  - Left arm: S4 already on forearm, direct offset computation

Tracks: hand segment + forearm segment → wrist joint angle

### Mode 3: Full arm [FUTURE]
Sensors: S1=right hand, S2=left hand, S3=right upper arm, S4=left upper arm
Hand + forearm bracketed (wrist immobilized) → one rigid body per side

Landmarks digitized:
- Hand+forearm: MCP, wrist, elbow → relative to hand sensor (S1/S2)
- Upper arm: elbow, shoulder → relative to upper arm sensor (S3/S4)
  - S3 acts as pointer first, then attaches to upper arm (button press finalizes)
  - Same deferred-conversion trick as Mode 2 step 6, extended to shoulder

Tracks: hand+forearm segment + upper arm segment → elbow angle + shoulder angle

---

## Game Screen
- Top-down view of workspace (Y = horizontal, Z = depth)
- Hand cursors: circle, size/color varies with X (height)
- Target: circle on workspace
- Dummy mode (no Liberty connected) for UI testing

---

## Reaching Mechanic (TBD)
- [ ] How is "reached" defined?
- [ ] Return to start after each reach?
- [ ] Time limit?
- [ ] Audio/visual feedback?

---

## Game Settings (TBD)
- [ ] Participant ID / session name
- [ ] Number of targets / trials
- [ ] Target positions (fixed or random?)
- [ ] Target size
- [ ] Which hand(s) used

---

## Data Logging (TBD)
- [ ] Full trajectory or endpoint only?
- [ ] Timestamps?
- [ ] CSV output?

---

## File Structure
```
Liberty/
├── PLAN.md
├── ReachingGame/
│   ├── main.py
│   ├── liberty_reader.py   # sensor reading + dummy mode
│   ├── digitizer.py        # rigid body math (Mode 1 first)
│   └── screens/
│       ├── menu.py
│       ├── setup.py
│       └── game.py
└── CalibrationRelated/
    └── ...
```

---

## Implementation Order
1. liberty_reader.py (dummy mode first, real pipe second)
2. main.py + menu.py (main menu with all items)
3. setup.py (Mode 1 digitization)
4. game.py (cursor display, no targets yet)
5. Space Calibration menu integration
6. Game mechanics + settings (TBD)
7. Mode 2, Mode 3 (future)
