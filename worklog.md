# ReachLab Worklog

---

## 2026-05-06

### Calibration Review
- Analyzed X values from calibration_20260505_181600.csv
- Identified 3 outlier points (Y=0/Z=14, Y=0/Z=18, Y=12/Z=18) — likely sensor placement errors
- Confirmed X drift across Z axis is minor (~0.3in over 16in), likely EM field distortion not source tilt
- Created remeasure_outliers.py to re-measure the 3 suspicious points
- Z=22 row intentionally skipped in original calibration

### Liberty Hardware
- Confirmed LED behavior: red/green alternating = EM interference detected
- Confirmed green LED when sensor is above table (normal use zone), red when below source level
- PiMgr must be running separately to expose named pipe — Pygame app reads from pipe only

### Environment Setup
- Installed Python 3.12.10 via winget (3.14 too new for pygame wheels)
- Created .venv312 with pygame 2.6.1 + pygame_gui 0.6.14

### ReachLab App — Initial Build
- Finalized 3-mode digitization design in PLAN.md:
  - Mode 0: Skip (raw sensor position)
  - Mode 1: MCP only (implement first)
  - Mode 2/3: Wrist / Full Arm (future)
- Created folder structure: ReachingGame/main.py, app_state.py, liberty_reader.py, screens/
- Main menu with 7 items: Start, Environment, Digitization, Game, Targets, Sessions, Quit
- Liberty status indicator (CONNECTED / DISCONNECTED / DUMMY MODE)
- Testing Mode toggle switch (bottom right, pill-shaped, ON=dark bg / OFF=light bg)
- Dummy mode: mouse controls right hand cursor in game screen
- LibertyReader always runs background thread; dummy flag toggleable at runtime
- Click debounce (350ms) on toggle switch to prevent rapid firing

---

## 2026-05-07

### Framework Migration: Pygame → PyQt5
- Switched from Pygame+pygame_gui to PyQt5 for native table widget support
- Reason: Target/Session screens require editable tables, pygame_gui has none
- Confirmed PyQt5 is lightweight enough for Mac Mini 2014 target hardware
- Kept LibertyReader background thread architecture unchanged

### Task-Based Architecture
- Introduced `tasks/` folder structure for multi-game-mode support
- Each task (e.g. `reaching_task.py`) owns its screens under `tasks/reaching/`
- Menu dropdown selects task type; Targets/Sessions/Game route to task-specific screens
- Adding a new task = create `tasks/new_task.py` + `tasks/new_task/` folder + add to TASKS list in main.py
- `screens/` now contains only shared UI: `menu.py`, `utils.py`

### Menu Screen
- App name: ReachLab; title fixed black text
- Status indicator: DUMMY MODE / CONNECTED / DISCONNECTED (500ms poll)
- Testing Mode toggle (bottom-right): ON = dark bg, OFF = light bg; bg only changes, text never changes
- Task dropdown: auto-built from TASKS list (currently: Reaching Task)
- Data folder selector (Browse button) below dropdown; Start blocked if no folder selected
- Sessions button blocked if no targets configured
- Dummy mode ON: auto-fills data folder (Liberty/test), 1 target, 10 trials
- Dummy mode OFF: clears all auto-fills back to blank

### Target Screen (tasks/reaching/targets.py)
- QTableWidget: ID, Angle(°), Distance(cm), Diameter(cm)
- Buttons (right side): Add Row, Delete Row, All Clear, Save CSV, Load CSV
- All cells center-aligned; Delete Row falls back to last row if none selected
- CooldownButton (200ms) on all buttons to prevent double-click

### Session Screen (tasks/reaching/sessions.py)
- QTableWidget: #, Hand, Target ID, Hold(s), Wait(s), Move(s), Instruction
- Buttons: Add Row, Delete Row, Duplicate (×N spinbox), All Clear, Randomize, Save CSV, Load CSV
- Multi-row select (Ctrl/Shift+click) for Delete and Duplicate
- Randomize: Fisher-Yates shuffle in-place
- Back button validates target IDs — warns and blocks if session references unregistered target
- Sessions button on menu blocked if no targets exist

### Game Screen (tasks/reaching/game.py)
- Full-screen on Start, returns to 1280×720 on ESC
- Workspace: 86.36 × 55.88 cm (34 × 22 inches converted)
- Black background, system cursor hidden, red dot = mouse in dummy mode
- **Calibration phase**: "Set your home position. Press SPACE to confirm."
- **Trial state machine** (per blueprint):
  - MoveToStart → HoldInStart → ShowDirection → Executing → Feedback → next trial
  - Home zone radius: 3 cm
  - Home circle: gray, black border (2px) when cursor inside
  - Target circle: visible from MoveToStart onwards (gray)
  - ShowDirection: instruction text only at bottom center ("REACH" / "REST", black)
  - Go cue: "GO!" at bottom center, first 0.6s of Executing
  - Feedback: frozen cursor (red dot) + "GOOD"(green) / "BAD"(red) at top center
- Angle convention: 0° = right (+Y), 90° = forward (+Z), full 0–359°
- Session complete screen on last trial done

---

## 2026-05-08

### Calibration Screen — Major Updates

**Grid density**
- Cols/Rows spinbox 제거 → Sparse (8 in) / Dense (4 in) 콤보박스로 교체
- 매트 크기 ÷ spacing으로 cols/rows 자동 계산, 점 개수 실시간 표시
- 그리드 엣지 여백: inch 모드 1 in / cm 모드 5 cm 오프셋 (코너 띄워서 시작)

**키 조작**
- T = 현재 지점 등록 + 자동 다음 이동 (Start 버튼 불필요, 화면 열리면 바로 T 대기)
- R = 이전 지점 undo
- Y = 현재 지점 skip

**Quiver plot (벡터장 시각화)**
- known position → measured position 방향 화살촉 화살표
- 절대값 기준 색상: 초록 <0.3 cm / 노랑 0.3–0.6 / 주황 0.6–0.9 / 빨강 ≥0.9 cm
- 화살표 끝에 오차 수치 표시 (14pt)

**캘리브레이션 persistence**
- Save → calibrated matrix/ 타임스탬프 파일 + ReachingGame/last_calibration.json 동시 저장
- 앱 재시작 후 Calibration 화면 열면 last_calibration.json 자동 복원
- Reset → 마지막 저장 캘리브레이션 복원 (없으면 새로 시작)

**기타**
- RMS/Max 통계 cm + inch 이중 단위
- Instruction에 좌표 cm + inch 이중 단위
- S1 커서 크기 50% 확대
- 메뉴/환경/캘리브레이션/세션/타겟 화면 폰트 전체 +2pt

### UI — Menu/Environment (이전 세션 포함 정리)
- Liberty 3단계 상태: DISCONNECTED / CONNECTED (pipe open) / RUNNING (data streaming)
- 더미 모드 표시: 타이틀 옆 "DUMMY MODE" 라벨 (제목 중앙 유지)
- 게임 중 "GAME IN PROGRESS" 표시 + 모든 컨트롤 lock
- S1–S4 센서 활성 표시 (초록/빨강)
- Environment: Reset(저장값 복원), Center, Max Fit, Scale spinbox, Apply 버튼
- Calibration 버튼 메뉴에 추가 (Environment 아래)

---

## Next Session

**Digitization (MCP joint recording)**
- S1 (오른손), S2 (왼손), S3 (포인터)로 MCP 관절 위치 기록
- 센서 오프셋 계산 → 손가락 끝 위치 추정
- PLAN.md 참고
