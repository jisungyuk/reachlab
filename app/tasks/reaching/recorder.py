import csv
import os
from datetime import datetime

from digitizer import track_mcp

# mcp kept as-is; wrist/elbow are derived (midpoint of their lateral/medial
# digitized points), shoulder is the single acromion point (no pair).
LANDMARKS = ('mcp',
             'wrist', 'wrist_lateral', 'wrist_medial',
             'elbow', 'elbow_lateral', 'elbow_medial',
             'shoulder')


def hand_folder(hand):
    return '01' if hand == 'right' else '02'


def ensure_session_dir(state):
    base    = state.data_dir if state.data_dir else os.path.expanduser('~')
    pid     = state.participant_id or 'unknown'
    stamp   = datetime.now().strftime('%Y%m%d_%H%M%S')
    session_dir = os.path.join(base, pid, f'session_{stamp}')
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


def _midpoint(a, b):
    if a is None or b is None:
        return None
    return [(a[i] + b[i]) / 2.0 for i in range(3)]


def _track_if_present(sensor, offset):
    if sensor is None or offset is None:
        return None
    return track_mcp(sensor, offset)


def live_landmarks(state, liberty, hand):
    """Return {landmark: [x, y, z]} (raw cm, sensor frame) for whichever
    landmarks the current dig_mode actually tracks for the given hand
    ('right' or 'left'). Landmarks not available in this mode are omitted."""
    out  = {}
    mode = state.dig_mode
    side = 'R' if hand == 'right' else 'L'

    if mode == 0:
        sensor_n = state.dig_sensor_right if hand == 'right' else state.dig_sensor_left
        s = liberty.get_sensor(sensor_n)
        if s is not None:
            out['mcp'] = [s.x * 2.54, s.y * 2.54, s.z * 2.54]
        return out

    if mode == 1:
        sensor_n = state.dig_sensor_right if hand == 'right' else state.dig_sensor_left
        offset   = state.mcp_offset_right if hand == 'right' else state.mcp_offset_left
        s = liberty.get_sensor(sensor_n)
        out['mcp'] = _track_if_present(s, offset)

    elif mode == 2:
        hand_sensor    = state.wrist_sensor_R_hand if hand == 'right' else state.wrist_sensor_L_hand
        forearm_sensor = state.wrist_sensor_R_ptr   if hand == 'right' else state.wrist_sensor_L_forearm
        sh = liberty.get_sensor(hand_sensor)
        sf = liberty.get_sensor(forearm_sensor)
        out['mcp']           = _track_if_present(sh, getattr(state, f'wrist_{side}_MCP'))
        out['wrist_lateral'] = _track_if_present(sf, getattr(state, f'wrist_{side}_RSP'))
        out['wrist_medial']  = _track_if_present(sf, getattr(state, f'wrist_{side}_USP'))
        out['elbow_lateral'] = _track_if_present(sf, getattr(state, f'wrist_{side}_LE'))
        out['elbow_medial']  = _track_if_present(sf, getattr(state, f'wrist_{side}_ME'))

    elif mode == 3:
        forearm_sensor = state.arm_sensor_R_forearm if hand == 'right' else state.arm_sensor_L_forearm
        upper_sensor   = state.arm_sensor_R_ptr      if hand == 'right' else state.arm_sensor_L_upper
        sf = liberty.get_sensor(forearm_sensor)
        su = liberty.get_sensor(upper_sensor)
        out['mcp']           = _track_if_present(sf, getattr(state, f'arm_{side}_MCP'))
        out['wrist_lateral'] = _track_if_present(sf, getattr(state, f'arm_{side}_RSP'))
        out['wrist_medial']  = _track_if_present(sf, getattr(state, f'arm_{side}_USP'))
        out['elbow_lateral'] = _track_if_present(su, getattr(state, f'arm_{side}_LE'))
        out['elbow_medial']  = _track_if_present(su, getattr(state, f'arm_{side}_ME'))
        out['shoulder']      = _track_if_present(su, getattr(state, f'arm_{side}_AP'))

    elif mode == 4:
        sh = liberty.get_sensor(state.arm4_sensor_hand)
        sf = liberty.get_sensor(state.arm4_sensor_forearm)
        su = liberty.get_sensor(state.arm4_sensor_upper)
        out['mcp']           = _track_if_present(sh, state.arm4_MCP)
        out['wrist_lateral'] = _track_if_present(sf, state.arm4_RSP)
        out['wrist_medial']  = _track_if_present(sf, state.arm4_USP)
        out['elbow_lateral'] = _track_if_present(su, state.arm4_LE)
        out['elbow_medial']  = _track_if_present(su, state.arm4_ME)
        out['shoulder']      = _track_if_present(su, state.arm4_AP)

    out['wrist'] = _midpoint(out.get('wrist_lateral'), out.get('wrist_medial'))
    out['elbow'] = _midpoint(out.get('elbow_lateral'), out.get('elbow_medial'))
    return {k: v for k, v in out.items() if v is not None}


def _format_header_value(v):
    if isinstance(v, float):
        return f'{v:.6f}'
    return str(v)


def write_trial(session_dir, hand, trial_index, meta, samples):
    """Single CSV per trial: '#'-prefixed metadata header, then a plain
    data table. samples: list of (t_ms, state_code, cursor_y, cursor_z,
    {landmark: [x, y, z]})."""
    folder = os.path.join(session_dir, hand_folder(hand))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f'trial_{trial_index:04d}.csv')

    fieldnames = ['t_ms', 'state', 'cursor_y', 'cursor_z']
    for lm in LANDMARKS:
        fieldnames += [f'{lm}_x', f'{lm}_y', f'{lm}_z']

    with open(path, 'w', newline='') as f:
        for key, value in meta.items():
            f.write(f'# {key}: {_format_header_value(value)}\n')
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t_ms, state_code, cursor_y, cursor_z, landmarks in samples:
            row = {
                't_ms':     f'{t_ms:.1f}',
                'state':    state_code,
                'cursor_y': f'{cursor_y:.3f}',
                'cursor_z': f'{cursor_z:.3f}',
            }
            for lm in LANDMARKS:
                pos = landmarks.get(lm)
                if pos is None:
                    row[f'{lm}_x'] = row[f'{lm}_y'] = row[f'{lm}_z'] = ''
                else:
                    row[f'{lm}_x'] = f'{pos[0]:.3f}'
                    row[f'{lm}_y'] = f'{pos[1]:.3f}'
                    row[f'{lm}_z'] = f'{pos[2]:.3f}'
            w.writerow(row)
