# Game Mode Build Blueprint
## RWR 구조 기반 — 새 게임 모드 단계별 구축 가이드

> 이 문서는 RWR 게임 모드의 아키텍처를 추상화한 템플릿이다.  
> 손 위치 데이터 소스로 Polhemus를 사용하는 시스템을 대상으로 작성됨.  
> Leap Motion 관련 부분은 `[INPUT]` 태그로 표시 — 대체 구현 필요.

---

## 전체 씬 흐름

```
MainMenu
  ↓ (RuntimeConfigStore에 타겟/세션 데이터 저장)
TargetTable 씬  ←→  CSV 저장/불러오기
  ↓
SessionTable 씬  ←→  CSV 저장/불러오기
  ↓ (RuntimeConfigStore.launchedFromMainMenu = true)
Game 씬
  ├─ 캘리브레이션 (홈 포지션 설정)
  ├─ Trial 1 → Trial 2 → ... → Trial N
  └─ End 씬 or 완료 화면
```

---

## Step 1: 데이터 구조 정의

### 1-1. 타겟 스펙 (RuntimeConfigStore에 추가)

```csharp
[System.Serializable]
public class MyTargetSpec {
    public int   id;            // 1-indexed
    public float angleDeg;      // 방향 (0=오른쪽, 90=앞쪽)
    public float distanceCm;    // 홈에서 거리 (cm)
    public float diameterCm;    // 타겟 크기 (cm)
}
```

### 1-2. 트라이얼 스펙 (RuntimeConfigStore에 추가)

```csharp
[System.Serializable]
public class MyTrialSpec {
    public int    trial;
    public string hand;           // "0"=left / "1"=right / "2"=either
    public string targetId;       // MyTargetSpec.id 참조
    public string instruction;    // "0"=rest / "1"=reach / ...
    public string holdDuration;   // start zone에 머무는 시간 (초)
    public string waitForGo;      // direction cue → Go 딜레이 (초)
    public string executing;      // 실행 윈도우 (초)
    // + 새 게임 모드에 필요한 추가 필드
}
```

### 1-3. RuntimeConfigStore에 등록

```csharp
// RuntimeConfigStore.cs에 추가
public List<MyTargetSpec> MyTargets = new List<MyTargetSpec>();
public List<MyTrialSpec>  MyTrials  = new List<MyTrialSpec>();
public Vector3 myCalibrationOrigin  = Vector3.zero;
public bool    myCalibrated         = false;
```

---

## Step 2: 타겟 테이블 씬 구축

**역할:** 타겟 목록(방향, 거리, 크기) 편집 + CSV 저장/불러오기

### 2-1. TargetRow_MY.cs

```csharp
public class TargetRow_MY : MonoBehaviour {
    public TMP_Text       idText;
    public TMP_InputField diameter;
    public TMP_InputField angleDeg;
    public TMP_InputField distanceCm;
    public Image          background;

    TargetTableController_MY owner;

    public void Init(TargetTableController_MY owner) { this.owner = owner; }
    public void SetId(int id) { idText.text = id.ToString(); }
    public void SelectMe()    { owner.SelectRow(this); }
    public void SetSelected(bool on) {
        background.color = on ? new Color(0.7f, 0.9f, 1f) : Color.white;
    }
}
```

### 2-2. TargetTableController_MY.cs 핵심 구조

```csharp
public class TargetTableController_MY : MonoBehaviour {
    [Header("UI")]
    public Transform       rowContainer;   // Scroll View Content
    public GameObject      rowPrefab;
    public Button          addBtn, deleteBtn, saveBtn, loadBtn;

    List<TargetRow_MY> rows = new List<TargetRow_MY>();
    TargetRow_MY       selected;
    int                nextId = 1;

    void Start()       { RestoreFromCache(); }
    void OnDisable()   { SnapshotToCache(); }   // 씬 전환 전 자동 저장

    public void AddTarget() { /* 기본값으로 row 생성 */ }
    public void DeleteSelected() { /* selected 제거 */ }
    public void SelectRow(TargetRow_MY row) { /* 선택 상태 업데이트 */ }
    public void SaveCsv() { /* 파일 다이얼로그 → CSV 쓰기 */ }
    public void LoadCsv() { /* 파일 다이얼로그 → CSV 읽기 → rows 재구성 */ }

    void SnapshotToCache() {
        var store = RuntimeConfigStore.Instance;
        store.MyTargets.Clear();
        foreach (var r in rows) {
            store.MyTargets.Add(new MyTargetSpec {
                id          = int.Parse(r.idText.text),
                angleDeg    = float.Parse(r.angleDeg.text),
                distanceCm  = float.Parse(r.distanceCm.text),
                diameterCm  = float.Parse(r.diameter.text)
            });
        }
    }

    void RestoreFromCache() {
        var store = RuntimeConfigStore.Instance;
        if (store.MyTargets.Count == 0) return;
        foreach (var spec in store.MyTargets) SpawnRow(spec);
    }
}
```

### CSV 형식 (타겟)

```
ID,angle_deg,distance_cm,diameter_cm
1,90,20,5
2,45,25,5
```

---

## Step 3: 세션 테이블 씬 구축

**역할:** 트라이얼 순서/파라미터 편집 + CSV 저장/불러오기

### 3-1. SessionRow_MY.cs

```csharp
public class SessionRow_MY : MonoBehaviour {
    public TMP_Text       trialIndex;
    public TMP_InputField hand;
    public TMP_InputField targetId;
    public TMP_InputField holdDuration;
    public TMP_InputField waitForGo;
    public TMP_InputField executing;
    public TMP_InputField instruction;
    // + 게임 모드별 추가 필드
    public Image          background;

    SessionTableController_MY owner;

    public void Init(SessionTableController_MY owner) { this.owner = owner; }
    public void SetIndex(int idx) { trialIndex.text = idx.ToString(); }
    public void SelectMe() { owner.SelectRow(this); }
    public void SetSelected(bool on) {
        background.color = on ? new Color(0.7f, 0.9f, 1f) : Color.white;
    }
}
```

### 3-2. SessionTableController_MY.cs 핵심 구조

```csharp
public class SessionTableController_MY : MonoBehaviour {
    // TargetTableController 패턴과 동일 —
    // 추가로: RandomizeTrials(), DuplicateSelected() 구현

    public void AddTrial()    { /* 기본값 row 생성 */ }
    public void RandomizeTrials() { /* Fisher-Yates shuffle */ }
    public void DuplicateSelected() { /* N번 복사 */ }
    public void SaveCsv()     { /* CSV 내보내기 */ }
    public void LoadCsv()     { /* CSV 불러오기 */ }

    void SnapshotToCache() {
        store.MyTrials.Clear();
        foreach (var r in rows) {
            store.MyTrials.Add(new MyTrialSpec {
                trial        = int.Parse(r.trialIndex.text),
                hand         = r.hand.text,
                targetId     = r.targetId.text,
                holdDuration = r.holdDuration.text,
                waitForGo    = r.waitForGo.text,
                executing    = r.executing.text,
                instruction  = r.instruction.text
            });
        }
    }
}
```

### CSV 형식 (세션)

```
#,hand,target,hold,wait,move,inst
1,1,1,0.5,2,3,1
2,1,2,0.5,2,3,1
```

---

## Step 4: [INPUT] Polhemus 입력 드라이버

Leap Motion의 `LeapFingerInput` 역할을 대체.  
Polhemus SDK/API에 맞게 구현.

```csharp
public class PolhemusInput : MonoBehaviour {
    // Polhemus SDK 연결 설정
    public string port;         // 시리얼 포트 또는 USB 설정

    // 외부에서 읽는 값
    public Vector3    handPosition  { get; private set; }  // MCP 또는 손목 위치
    public Quaternion handRotation  { get; private set; }  // 손 방향
    public bool       isTracking    { get; private set; }  // 데이터 수신 중 여부

    void Update() {
        // Polhemus로부터 최신 위치/방향 읽기
        // handPosition, handRotation, isTracking 업데이트
    }
}
```

**GameSessionController와 TrialGameController에서는**  
`LeapFingerInput.indexMcp.position` 대신 `PolhemusInput.handPosition`을 참조하면 됨.

---

## Step 5: 트라이얼 컨트롤러 (State Machine)

**파일명:** `TrialGameController_MY.cs`

### 5-1. 상태 정의

```csharp
enum TrialState {
    Idle,
    MoveToStart,    // 손이 홈 포지션으로 이동 대기
    HoldInStart,    // 홈에서 holdDuration 동안 유지
    ShowDirection,  // 방향/타겟 표시, goDelay 대기
    Executing,      // 실제 움직임 윈도우
    Feedback,       // GOOD/BAD 표시
    TrialDone
}
```

### 5-2. 핵심 공개 메서드

```csharp
public void ConfigureAndBegin(
    Vector3 startPos,
    Vector3 targetPos,
    float   targetRadius,
    int     trialIndex,
    int     targetId,
    int     handMode,
    int     instruction,
    float   perTrialHoldDuration      = 0f,
    float   perTrialWaitForGo         = 0f,
    float   perTrialExecutingDuration = 0f
)
```

### 5-3. 상태 전환 로직

```
MoveToStart
  └─ [INPUT].handPosition이 startZone 안에 들어오면 → HoldInStart

HoldInStart
  ├─ holdTimer += Time.deltaTime
  ├─ 손이 zone 밖으로 나가면 → MoveToStart (reset)
  └─ holdTimer >= holdDuration → ShowDirection

ShowDirection
  ├─ readyTime = Time.time 기록
  ├─ 타겟/방향 표시
  ├─ 손이 zone 밖으로 나가면 → MoveToStart (reset)
  └─ Time.time >= readyTime + goDelay → Executing

Executing
  ├─ execTimer += Time.deltaTime
  └─ execTimer >= executionDuration → EvaluateOutcome() → Feedback

Feedback
  ├─ feedbackTimer += Time.deltaTime
  └─ feedbackTimer >= feedbackDuration → TrialDone

TrialDone
  └─ OnTrialFinished 이벤트 발생
```

### 5-4. 존 판정 (XZ 평면)

```csharp
bool HandInZone(Vector3 center, float radius) {
    Vector3 pos = polhemusInput.handPosition;
    float dx = pos.x - center.x;
    float dz = pos.z - center.z;
    return dx * dx + dz * dz <= radius * radius;
}
```

### 5-5. 아웃컴 판정

```csharp
void EvaluateOutcome() {
    switch (currentInstruction) {
        case INST_REST:  outcomeGood = HandInZone(startPos, startRadius);  break;
        case INST_REACH: outcomeGood = HandInZone(targetPos, targetRadius); break;
        // + 새 모드에 맞는 판정 추가
    }
}
```

### 5-6. 이벤트

```csharp
public event Action OnTrialFinished;  // GameSessionController가 구독
```

### 5-7. 타이밍 파라미터 (Inspector)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `holdDuration` | 0.5s | 홈에서 유지 시간 |
| `goDelay` | 2.0s | 방향 표시 후 Go까지 딜레이 |
| `executionDuration` | 3.0s | 실행 윈도우 |
| `feedbackDuration` | 1.0s | GOOD/BAD 표시 시간 |
| `startRadius` | 0.03m | 홈 존 반경 |

---

## Step 6: 세션 컨트롤러

**파일명:** `GameSessionController_MY.cs`

### 6-1. 초기화 흐름

```csharp
void Start() {
    trialController.gameObject.SetActive(false);
    ShowCalibrationScreen();
}
```

### 6-2. 캘리브레이션

```csharp
void ShowCalibrationScreen() {
    // "홈 포지션에 손을 놓고 SPACE를 누르세요" 표시
    // [INPUT] isTracking 표시
    state = SessionState.Calibrating;
}

void ConfirmCalibration() {
    // [INPUT] 현재 손 위치를 홈으로 설정
    Vector3 origin = polhemusInput.handPosition;
    store.myCalibrationOrigin = origin;
    store.myCalibrated = true;

    BuildTrials(origin);
    state = SessionState.Running;
    trialController.gameObject.SetActive(true);
    StartNextTrial();
}
```

### 6-3. 타겟 위치 계산 (polar → world)

```csharp
Vector3 PolarToWorld(Vector3 origin, float angleDeg, float distanceCm) {
    float rad  = angleDeg * Mathf.Deg2Rad;
    float dist = distanceCm / 100f;
    return new Vector3(
        origin.x + dist * Mathf.Cos(rad),
        origin.y,
        origin.z + dist * Mathf.Sin(rad)
    );
}
```

### 6-4. 트라이얼 순서 관리

```csharp
void StartNextTrial() {
    currentIndex++;
    if (currentIndex >= trials.Length) { LoadEndScene(); return; }
    var cfg = trials[currentIndex];
    trialController.ConfigureAndBegin(
        cfg.startPos, cfg.targetPos, cfg.targetRadius,
        cfg.trialIndex, cfg.targetId, cfg.handMode, cfg.instruction,
        cfg.holdDuration, cfg.waitForGo, cfg.executingDuration
    );
}

void HandleTrialFinished() { StartNextTrial(); }
```

### 6-5. 재캘리브레이션 (선택사항)

```csharp
// SHIFT+SPACE (MoveToStart 상태일 때만)
void Recalibrate() {
    Vector3 origin = polhemusInput.handPosition;
    store.myCalibrationOrigin = origin;
    // 모든 trial config의 startPos/targetPos 재계산
    currentIndex = -1;
    StartNextTrial();
}
```

---

## Step 7: TTL 출력 (선택사항)

**목적:** EMG 머신 또는 peripheral stimulator와 타이밍 동기화.  
LabChart FRO 시스템은 불필요 — 단순 serial TTL pulse만 구현.

### 구현 방법

```csharp
// TrialGameController_MY.cs에 추가
[Header("TTL")]
[SerializeField] string ttlComPort        = "";     // 비워두면 TTL 비활성화
[SerializeField] int    ttlChannel        = 1;      // 채널 (1–8)
[SerializeField] int    ttlPulseDurationMs = 100;   // 펄스 지속 시간 (ms)

SerialPort ttlPort;

void Awake() {
    if (!string.IsNullOrEmpty(ttlComPort)) {
        ttlPort = new SerialPort(ttlComPort, 9600);
        ttlPort.Open();
    }
}

void FireTtlPulse() {
    if (ttlPort == null || !ttlPort.IsOpen) return;
    byte mask = (byte)(1 << (ttlChannel - 1));
    ttlPort.Write(new byte[] { mask }, 0, 1);
    StartCoroutine(ResetTtl(ttlPulseDurationMs / 1000f));
}

IEnumerator ResetTtl(float delay) {
    yield return new WaitForSeconds(delay);
    ttlPort.Write(new byte[] { 0x00 }, 0, 1);
}

void OnDestroy() {
    if (ttlPort != null && ttlPort.IsOpen) ttlPort.Close();
}
```

### 언제 fire하나

Go cue 시점, 또는 필요한 타이밍에 `FireTtlPulse()` 호출.  
정밀한 timing offset이 필요하면 `ttlPlannedTime = targetTime - offsetSec` 패턴 사용 (RWR 참고).

---

## Step 8: 데이터 로깅

**패턴:** 매 프레임 또는 state 전환 시 CSV에 기록.

```csharp
// 로그 헤더
// time, state, hand_x, hand_y, hand_z, target_x, target_z, outcome

// 매 Update에서:
logger.WriteRow(
    Time.time,
    currentState.ToString(),
    polhemusInput.handPosition,
    targetPos,
    outcomeGood ? 1 : 0
);
```

---

## Step 9: 씬 구성

### 8-1. 필요한 GameObject

| GameObject | 컴포넌트 | 역할 |
|-----------|---------|------|
| `[INPUT] PolhemusManager` | PolhemusInput | 손 위치 데이터 공급 |
| `TrialController` | TrialGameController_MY | 상태 기계 |
| `SessionController` | GameSessionController_MY | 트라이얼 시퀀싱 |
| `RuntimeConfigStore` | RuntimeConfigStore | 씬 간 데이터 전달 |
| `StartSphere` | MeshRenderer | 홈 존 시각화 |
| `TargetSphere` | MeshRenderer | 타겟 존 시각화 |
| Canvas | TMP_Text (instruction, debug) | UI |

### 8-2. 인스펙터 연결 체크리스트

- [ ] `TrialGameController_MY.polhemusInput` → PolhemusInput 컴포넌트
- [ ] `TrialGameController_MY.startSphere` → StartSphere GameObject
- [ ] `TrialGameController_MY.targetSphere` → TargetSphere GameObject
- [ ] `TrialGameController_MY.instructionText` → Canvas TMP_Text
- [ ] `GameSessionController_MY.trialController` → TrialGameController_MY
- [ ] `GameSessionController_MY.polhemusInput` → PolhemusInput 컴포넌트

---

## Step 10: Build 순서 권장

1. **RuntimeConfigStore** 에 새 spec 추가 (데이터 구조 먼저 확정)
2. **TargetRow_MY + TargetTableController_MY** 빌드 + CSV 테스트
3. **SessionRow_MY + SessionTableController_MY** 빌드 + CSV 테스트
4. **[INPUT] PolhemusInput** 빌드 + 단독 테스트 (handPosition 출력 확인)
5. **TrialGameController_MY** 빌드 — PolhemusInput 없이 더미 Vector3로 먼저 테스트
6. **GameSessionController_MY** 빌드 + 전체 flow 테스트
7. 씬 연결 + EditorBuildSettings에 씬 추가
8. MainMenu에서 새 게임 모드 버튼/분기 추가

---

## RWR에서 재사용 가능한 패턴 (변경 없이)

| 패턴 | RWR 파일 | 재사용 방법 |
|------|---------|-----------|
| Singleton 씬 간 데이터 전달 | `RuntimeConfigStore.cs` | 새 spec 필드만 추가 |
| Polar→World 변환 | `GameSessionController_RWR.cs` | 그대로 복사 |
| Fisher-Yates shuffle | `SessionTableController_RWR.cs` | 그대로 복사 |
| CSV 파싱 헬퍼 (hand, inst) | `GameSessionController_RWR.cs` | ParseHand(), ParseInstruction() |
| XZ 평면 존 판정 | `TrialGameController_RWR.cs` | 그대로 복사 |
| 일시정지 로직 | `TrialGameController_RWR.cs` | 타이머 기준점 이동 방식 |

---

## [INPUT] 교체 포인트 요약

RWR에서 Leap Motion을 사용하는 부분을 Polhemus로 교체해야 할 위치:

| RWR 코드 | 교체 대상 |
|---------|---------|
| `leapInput.indexMcp.position` | `polhemusInput.handPosition` |
| `leapInput.hasIndexJointData` | `polhemusInput.isTracking` |
| `leapInput.useLeftHand` | `polhemusInput.handSide` 또는 설정값 |
| Calibration 시 MCP 위치 | `polhemusInput.handPosition` |
| Debug: MCP 위치 표시 | `polhemusInput.handPosition` |
