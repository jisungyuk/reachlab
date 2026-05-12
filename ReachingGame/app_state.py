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
        self.digitization_mode = 0
        self.mcp_offset_right = None
        self.mcp_offset_left = None
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
        self.env_rect_x        = None   # monitor rect position/size in desk-cm coords
        self.env_rect_y        = None
        self.env_rect_w        = None
        self.env_rect_h        = None

        # Sensor origin offset in cm (set once when sensor is at desk bottom-left corner)
        self.sensor_y_offset   = 0.0
        self.sensor_z_offset   = 0.0

    _PERSIST_KEYS = (
        'WORKSPACE_Y_MIN', 'WORKSPACE_Y_MAX',
        'WORKSPACE_Z_MIN', 'WORKSPACE_Z_MAX',
        'env_mon_size', 'env_mon_unit', 'env_mon_ratio_idx',
        'env_desk_w', 'env_desk_h', 'env_desk_unit',
        'env_rect_x', 'env_rect_y', 'env_rect_w', 'env_rect_h',
        'sensor_y_offset', 'sensor_z_offset',
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
