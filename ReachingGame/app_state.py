import os
import json

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


class AppState:
    def __init__(self):
        self.WORKSPACE_Y_MIN = 0.0
        self.WORKSPACE_Y_MAX = 86.36
        self.WORKSPACE_Z_MIN = 0.0
        self.WORKSPACE_Z_MAX = 55.88
        self.task_type = 'reaching'
        self.calibration_file = None
        self.participant_id = ""
        self.session_name = "session_001"
        self.data_dir = ""
        self.sample_rate_hz = 125
        self.targets = []
        self.target_radius_inch = 1.5

        # Environment screen state (persisted)
        self.env_mon_size      = 27.0
        self.env_mon_unit      = 'in'
        self.env_mon_ratio_idx = 0
        self.env_desk_w        = 86.36
        self.env_desk_h        = 55.88
        self.env_desk_unit     = 'cm'
        self.env_rect_x        = None
        self.env_rect_y        = None
        self.env_rect_w        = None
        self.env_rect_h        = None

        # Sensor origin offset in cm
        self.sensor_y_offset   = 0.0
        self.sensor_z_offset   = 0.0

        # Digitization — Mode 0: Cursor  (nothing below is persisted across restarts)
        self.dig_mode              = 0
        self.dig_hand_setup        = 2   # 0=Right, 1=Left, 2=Both
        self.dig_sensor_right      = 1
        self.dig_sensor_left       = 2

        # Digitization — Mode 1: MCP
        self.mcp_sensor_pointer    = 3
        self.mcp_offset_right      = None  # [x,y,z] in R.hand sensor local frame
        self.mcp_offset_left       = None  # [x,y,z] in L.hand sensor local frame

        # Digitization — Mode 2: Wrist
        self.wrist_sensor_L_hand    = 1
        self.wrist_sensor_R_hand    = 2
        self.wrist_sensor_L_forearm = 3
        self.wrist_sensor_R_ptr     = 4    # pointer first, then placed on R forearm
        # Left side offsets
        self.wrist_L_MCP = None  # [x,y,z] in L.Hand frame
        self.wrist_L_RSP = None  # [x,y,z] in L.Forearm frame
        self.wrist_L_USP = None
        self.wrist_L_LE  = None
        self.wrist_L_ME  = None
        # Right side offsets (final, after forearm finalization)
        self.wrist_R_MCP = None  # [x,y,z] in R.Hand frame
        self.wrist_R_RSP = None  # [x,y,z] in R.Forearm frame
        self.wrist_R_USP = None
        self.wrist_R_LE  = None
        self.wrist_R_ME  = None

        # Digitization — Mode 4: Full Single Arm
        self.arm4_sensor_hand    = 1
        self.arm4_sensor_forearm = 2
        self.arm4_sensor_upper   = 3
        self.arm4_sensor_trunk   = 4    # pointer first, then placed on trunk
        # Landmarks (single side — determined by dig_hand_setup at runtime)
        self.arm4_MCP    = None  # Hand frame
        self.arm4_USP    = None  # Forearm frame
        self.arm4_RSP    = None  # Forearm frame
        self.arm4_ME     = None  # UpperArm frame
        self.arm4_LE     = None  # UpperArm frame
        self.arm4_AP     = None  # UpperArm frame
        self.arm4_AP_opp = None  # Trunk frame (after finalize)

        # Digitization — Mode 3: Full Arm
        self.arm_sensor_L_forearm = 1
        self.arm_sensor_R_forearm = 2
        self.arm_sensor_L_upper   = 3
        self.arm_sensor_R_ptr     = 4    # pointer first, then placed on R upper arm
        # Left side offsets
        self.arm_L_MCP = None  # [x,y,z] in L.Forearm frame
        self.arm_L_RSP = None  # [x,y,z] in L.Forearm frame
        self.arm_L_USP = None  # [x,y,z] in L.Forearm frame
        self.arm_L_ME  = None  # [x,y,z] in L.UpperArm frame
        self.arm_L_LE  = None  # [x,y,z] in L.UpperArm frame
        self.arm_L_AP  = None  # [x,y,z] in L.UpperArm frame
        # Right side offsets (final, after upper arm finalization)
        self.arm_R_MCP = None  # [x,y,z] in R.Forearm frame
        self.arm_R_RSP = None  # [x,y,z] in R.Forearm frame
        self.arm_R_USP = None  # [x,y,z] in R.Forearm frame
        self.arm_R_ME  = None  # [x,y,z] in R.UpperArm frame
        self.arm_R_LE  = None  # [x,y,z] in R.UpperArm frame
        self.arm_R_AP  = None  # [x,y,z] in R.UpperArm frame

    _PERSIST_KEYS = (
        'WORKSPACE_Y_MIN', 'WORKSPACE_Y_MAX',
        'WORKSPACE_Z_MIN', 'WORKSPACE_Z_MAX',
        'env_mon_size', 'env_mon_unit', 'env_mon_ratio_idx',
        'env_desk_w', 'env_desk_h', 'env_desk_unit',
        'env_rect_x', 'env_rect_y', 'env_rect_w', 'env_rect_h',
        'sensor_y_offset', 'sensor_z_offset',
        # Digitization fields are intentionally NOT persisted —
        # they reset to defaults on every program start.
        # Use the Save/Load buttons inside Digitization for crash recovery.
    )

    def save_config(self):
        data = {k: getattr(self, k) for k in self._PERSIST_KEYS}
        with open(_CONFIG_PATH, 'w') as f:
            json.dump(data, f, indent=2)

    def load_config(self):
        if not os.path.exists(_CONFIG_PATH):
            return
        try:
            with open(_CONFIG_PATH) as f:
                data = json.load(f)
            for k, v in data.items():
                if k in self._PERSIST_KEYS:
                    setattr(self, k, v)
        except Exception:
            pass
