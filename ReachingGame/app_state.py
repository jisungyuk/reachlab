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

        # Digitization — Mode 0: Cursor
        self.dig_mode              = 0
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
        self.wrist_L_MCP = None  # [x,y,z] in L.hand (S1) frame
        self.wrist_L_RSP = None  # [x,y,z] in L.forearm (S3) frame
        self.wrist_L_USP = None
        self.wrist_L_LE  = None
        self.wrist_L_ME  = None
        # Right side offsets (final, after forearm finalization)
        self.wrist_R_MCP = None  # [x,y,z] in R.hand (S2) frame
        self.wrist_R_RSP = None  # [x,y,z] in R.forearm (S4) frame
        self.wrist_R_USP = None
        self.wrist_R_LE  = None
        self.wrist_R_ME  = None

    _PERSIST_KEYS = (
        'WORKSPACE_Y_MIN', 'WORKSPACE_Y_MAX',
        'WORKSPACE_Z_MIN', 'WORKSPACE_Z_MAX',
        'env_mon_size', 'env_mon_unit', 'env_mon_ratio_idx',
        'env_desk_w', 'env_desk_h', 'env_desk_unit',
        'env_rect_x', 'env_rect_y', 'env_rect_w', 'env_rect_h',
        'sensor_y_offset', 'sensor_z_offset',
        'dig_mode', 'dig_sensor_right', 'dig_sensor_left',
        'mcp_sensor_pointer', 'mcp_offset_right', 'mcp_offset_left',
        'wrist_sensor_L_hand', 'wrist_sensor_R_hand',
        'wrist_sensor_L_forearm', 'wrist_sensor_R_ptr',
        'wrist_L_MCP', 'wrist_L_RSP', 'wrist_L_USP', 'wrist_L_LE', 'wrist_L_ME',
        'wrist_R_MCP', 'wrist_R_RSP', 'wrist_R_USP', 'wrist_R_LE', 'wrist_R_ME',
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
