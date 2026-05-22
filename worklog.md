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

---

## 2026-05-12

### GitHub
- 프로젝트 전체 github.com/jisungyuk/reachlab (public)에 업로드

### Environment Screen
- Monitor zone을 책상 경계 밖으로 이동/확장 가능하게 변경 (Max Fit은 유지)
- 드래그 시 size는 유지하고 position만 clamp (`_clamp_pos_only`)
- 재시작 후 oversized rect 유지 (restore_rect에서 _clamp 호출 제거)
- Player 마커 추가: 책상 상단 중앙에 빨간 삼각형 + "Player" 라벨

### Sensor Origin Offset
- Environment 화면에 "Set Origin" 버튼 추가 (S1 기준, 3초 카운트다운 + 비프음)
- `sensor_y_offset`, `sensor_z_offset` config.json에 저장/복원
- 현재 설정된 origin 값 라벨로 상시 표시
- 게임/캘리브레이션/digitization 모든 센서 읽기에 offset 적용

### Digitization Screen — 전체 구현
- **app_state.py**: 모드별 필드 정리; dig 관련 필드는 config 비저장 (매 실행 시 초기화)
- **digitizer.py** 신규: `rotation_matrix`, `compute_offset`, `finalize_forearm`, `track_mcp`
- **Mode 0 (Cursor)**: Right/Left hand 센서 지정 드롭다운
- **Mode 1 (MCP)**:
  - Sensor Assignment (Right/Left/Pointer), 상호 배타 (pointer 제외)
  - 즉시 기록 + 비프 (카운트다운 없음)
  - 단축키: `1` = Right MCP, `F1` = Left MCP
  - 자동저장: `data_dir/digitization_mode1.json` (매 기록 후)
  - Save / Load 버튼
  - Live MCP Position 실시간 추적
- **Mode 2 (Wrist)**: 4 센서 지정, 10 landmark record + Finalize Right Forearm
- 공통: S1–S4 항상 표시, 지정 센서 초록 / 비지정 회색, 드롭다운 변경 시 실시간 색 반영

### Digitization — Mode 선택 UX
- Apply 버튼으로 모드 확정; 옆에 "Current: Mode X" 표시
- 첫 진입 시 Mode 0 자동 적용; Apply 후 프로그램 내 재진입 시 그 모드 유지
- data_dir 미설정 시 Digitization 진입 차단 (경고 다이얼로그)

### Digitization Canvas (Mode 0 / 1)
- 상단 뷰 (Y = 좌우, Z 반전으로 플레이어 = 아래, 모니터 = 위)
- Monitor rect 중심으로 뷰 정렬, monitor rect 기준 스케일
- Right = 빨강, Left = 파랑; 센서 도트 + MCP 도트 + 연결선

---

## 2026-05-13

### Digitization Canvas — Scale Fix
- 캔버스 배율을 auto-fit에서 실제 크기의 30%로 변경
- `_VIEW_RATIO = 0.30` 상수 도입; `env_mon_size` + `env_mon_ratio_idx` + `QScreen` 픽셀 너비로 px/cm 동적 계산
- 모니터 설정이 바뀌면 배율 자동 재계산 (하드코딩 없음)

### Digitization Mode 2 (Wrist) — Frame 수정
- RSP/USP 기록 기준을 Hand 센서 → **Forearm 센서**로 변경 (왼쪽/오른쪽 모두)
- MCP만 Hand 센서 기준, 나머지 RSP/USP/ME/LE 전부 Forearm 센서 기준
- Finalize(키 6) 대상: ME/LE → **RSP/USP/ME/LE 전부** R.Forearm으로 변환
- 프레임 라벨 텍스트 수정: RSP/USP는 항상 Forearm frame 표시
- Finalize 후 스크롤 위치 유지: `_rebuild_content()` 제거 → status label 직접 업데이트

### Digitization Mode 3 (Full Arm) — 전체 구현
- **센서 배치**: L.Forearm, R.Forearm, L.UpperArm, R.Ptr(→R.UpperArm)
- **랜드마크**: MCP, RSP, USP (Forearm 기준) / ME, LE, AP (UpperArm 기준)
- **왼쪽**: 즉시 Forearm/UpperArm 센서 기준으로 저장
- **오른쪽**: MCP/RSP/USP → R.Forearm 즉시 저장; ME/LE/AP → `_arm_R_tmp` 임시 저장 후 키 7(Finalize)로 R.UpperArm 변환
- **단축키**: 1–6/F1–F6 랜드마크, 7 = Finalize Right Upper Arm
- **캔버스**: 4센서 표시 + 랜드마크 도트 + 연결선 + skeleton (forearm→wrist joint→elbow joint→AP)
- **저장**: `digitization_mode3.json`
- `app_state.py`에 Mode 3 전용 필드 추가 (`arm_sensor_*`, `arm_L/R_*`)

### Digitization UX 개선
- Finalize 완료음: 단음 비프 → C 장조 아르페지오 (도미솔도, ~0.5초)
- Mode 1 캔버스에 Pointer 센서 회색 점으로 표시

---

## 2026-05-20

### Digitization Mode 4 (Full Single Arm) — Full Implementation

- **app_state.py**: Mode 4 fields already added in previous session (`arm4_sensor_*`, `arm4_MCP/USP/RSP/LE/ME/AP/AP_opp`)
- **digitization.py** — complete Mode 4 implementation:
  - Added `ARM4_LANDMARKS`, `ARM4_LM_FULL`, `_ARM4_LM_IDX` constants
  - Added `Full Single Arm (Mode 4)` entry to MODES dropdown
  - `__init__`: `_arm4_status_lbls`, `_arm4_tmp` dicts; `_sc8` shortcut (key 8 = Finalize Trunk); `_sc7` re-routed to new `_shortcut_key7`
  - `_on_apply`: Mode 4 disables Both option in hand combo, defaults to Right; re-enables Both when switching to other modes
  - `_mcp_field`: mode 4 returns `arm4_MCP`
  - Shortcut routing: key 1 → MCP; keys 2-5 remapped (RSP↔USP, ME↔LE) for mode 4; key 6 → AP; key 7 → AP_opp; key 8 → Finalize Trunk
  - F-keys (left side) inactive in mode 4 — mode 4 is single-arm only
  - `_build_arm4`: single-column landmark grid (7 cells), Finalize Trunk [8], Save/Load/Clear, canvas
  - Frame assignments: MCP → Hand, USP/RSP → Forearm, ME/LE/AP → UpperArm, AP_opp → Trunk (after Finalize)
  - `AP_opp` workflow: pointer records in UpperArm frame (`_arm4_tmp`), then place S4 on trunk, key 8 finalizes to Trunk frame via `finalize_forearm`
  - Auto-save to `digitization_mode4.json`
  - Canvas: 4-sensor display + landmark dots + wrist/elbow joint skeleton + AP line

---

## 2026-05-22

### Workspace Task — Envelope & Ghost System Overhaul

**60-bin forward-only envelope**
- 기존 120-bin (forward 60 zeroed) → 60-bin (0°–180°, 3°/bin)으로 변경
- bin 0 = 정면 0°, bin 59 = 178.5°; atan2 범위 [0, π]에 깔끔하게 대응

**Bin interpolation**
- 연속된 두 샘플 사이에 직선 보간 추가
- 각도 변화량 ÷ BIN_RAD + 2 스텝으로 분할 → 빠른 움직임에서도 빈 bin 없음

**Envelope center (중앙점)**
- 이전: raw start_pts 위치
- 변경: set_start의 Y + lateral_z의 교차점 = 진짜 기하학적 중앙점
- `_end_recording`에서 `sy = start_pts[arm][0]`, `sz = lateral_lines[arm]` 사용

**Polygon bottom closing (3-anchor)**
- 이전: 마지막 arc → 첫 arc 대각선 연결 → 바닥 열림
- 변경: 마지막 arc → (last_y, close_z) → (center_y, close_z) → (first_y, close_z) 3앵커
- lateral line에 깔끔하게 닿는 다각형 보장

**Max ghost mode 추가**
- 기존: Individual (최근 5개) / Average (running mean)
- 추가: Max (per-bin maximum across all trials)
- `game_settings.py` 콤보박스 및 설명 라벨 업데이트

**Center rebase**
- Shift+Space로 start를 다시 설정하면 기존 envelopes의 (sy, sz)를 새 중앙점으로 업데이트
- envelope 형태(bins)는 유지, origin만 이동

### Workspace Task — UX / Phase Improvements

**Center line**
- set_start 후 center_y 기준 수직선: z+2 cm → WORKSPACE_Z_MIN까지

**Guide line origin**
- 이전: raw start_pts에서 출발
- 변경: envelope center (start_pts.y, lateral_z) 교차점에서 출발

**wait_start UX**
- 커서가 start circle 밖 → "Return to start position."
- 커서가 start circle 안 → "Ready for the cue."
- start circle 밖이면 Space 무효 (안전장치)
- Shift+Space: 이전 center/lateral/circle 잔상 alpha 0.3으로 표시하고 set_start 재진입

**Elevation (x) feature**
- Sessions 테이블에 "Elevation (cm)" 컬럼 추가 (0이면 비활성)
- recording 중 x < threshold 1초 이상 → trial abort (wait_start로 복귀, 비프)
- wait_start에서 x 부족 시 Space 차단; "Raise your hand!" 경고 표시 (빨간 별도 줄)
- recording 중에도 x < threshold면 "Raise your hand!" 경고 (guideline은 계속 진행)
- 커서 색: x 부족 시 빨강, 정상 시 초록
- dummy + mouse 모드: 마우스 휠로 x 0.5 cm 단위 조절, 커서 아래 수치 표시

**Pause feature**
- ESC 첫 번째: pause (중앙 네모 "PAUSE" 깜박임, ~2Hz)
- Space: resume
- ESC 두 번째: 메뉴로 복귀
- "SPACE to resume" / "ESC to end the session" 안내 텍스트

**Backspace**: recording 중 누르면 trial 즉시 abort → wait_start

### Workspace Task — Results Display

- 우측 상단에 R avg / L avg (n=x) 항시 표시
- show_traj 단계에서 해당 trial 면적 (cm²) 상단 중앙 표시
- 세션 완료 화면에 R/L 평균 + n 크게 표시

### Main Menu — Start from Trial

- Start 버튼 아래 줄: "[ ] Start from trial ___" 체크박스 + 입력란
- 체크 안 된 상태: 입력란 비활성 (trial 1부터 시작)
- 체크 후 범위 밖 번호 입력 시 경고 다이얼로그
- `app_state.ws_start_trial` 연동

### Sampling Rate

- 기본값 125 Hz → 250 Hz로 변경 (타이머 4ms)
- reaching task 타이머도 동일하게 4ms로 통일
- 메뉴 sample rate spinbox를 read-only (회색 배경)로 변경
- 메뉴에 Liberty 실제 read rate 표시 (`liberty_rate_lbl`, 500ms 갱신)
- `liberty_reader.py`에 `get_read_rate()` 추가: station 1 패킷만 카운트, 최근 2초 평균
- `tools/measure_liberty_rate.py` 신규: 하드웨어 실제 측정률 측정 스크립트

### Game Settings — Elevation Abort Duration

- "Elevation Abort Duration" 슬롯 추가 (0.1–10.0 s, 기본 1.0 s)
- `app_state.ws_elev_dur` 연동; `game.py` 하드코딩 1.0 → state 참조로 교체

### Game Settings — Layout Redesign

- 각 섹션 제목을 별도 줄(13pt Bold)로 분리
- 컨트롤은 그 아래 줄에 12px indent
