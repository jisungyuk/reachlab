import os
import re
from datetime import datetime

from digitizer import track_mcp

# mcp kept as-is; wrist/elbow are derived (midpoint of their lateral/medial
# digitized points), shoulder is the single acromion point (no pair).
LANDMARKS = ('mcp',
             'wrist', 'wrist_lateral', 'wrist_medial',
             'elbow', 'elbow_lateral', 'elbow_medial',
             'shoulder')

# Shared output format (KinematicToolBox DATA_FORMAT.md, format_version 1).
# Every trial file carries all of these columns in this order, from every
# acquisition system; values a system does not measure are left blank.
FORMAT_VERSION = 1
OUTPUT_JOINTS  = ('idx', 'thb', 'mcp',
                  'wrist', 'wrist_lateral', 'wrist_medial',
                  'elbow', 'elbow_lateral', 'elbow_medial',
                  'shoulder')
COLUMNS = ['t_ms', 'state', 'ttl'] + [f'{j}_{a}' for j in OUTPUT_JOINTS for a in 'xyz']

AXES   = 'x=right, y=up, z=forward'
ORIGIN = 'liberty_transmitter_minus_sensor_offset'


def to_output_axes(p):
    """Liberty frame (x=up, y=right, z=forward) -> shared output frame
    (x=right, y=up, z=forward). Only the CSV writer uses this; everything
    inside the app keeps the Liberty frame."""
    return [p[1], p[0], p[2]]


def hand_folder(hand):
    return '01' if hand == 'right' else '02'


def ensure_session_dir(state):
    """<data_dir>/<participant>/session_NNN_YYYYMMDD, NNN = next free number
    in that participant folder."""
    base = state.data_dir if state.data_dir else os.path.expanduser('~')
    pid  = state.participant_id or 'unknown'
    root = os.path.join(base, pid)
    os.makedirs(root, exist_ok=True)
    latest = 0
    for name in os.listdir(root):
        m = re.match(r'session_(\d{3})(_|$)', name)
        if m:
            latest = max(latest, int(m.group(1)))
    stamp = datetime.now().strftime('%Y%m%d')
    session_dir = os.path.join(root, f'session_{latest + 1:03d}_{stamp}')
    os.makedirs(session_dir, exist_ok=True)
    return latest + 1, session_dir


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
        return f'{v:.3f}'
    if isinstance(v, (list, tuple)):
        return ','.join('' if c is None else f'{c:.3f}' for c in v)
    if v is None:
        return ''
    return str(v)


def _fmt(v):
    return '' if v is None else f'{v:.3f}'


def write_trial(session_dir, trial_index, used_hand, meta, samples):
    """Writes the trial to both hand folders (01 = right, 02 = left), as
    0001.csv, 0002.csv, ... The file of the hand that was not used keeps
    t_ms/state but has blank coordinates.
    meta: header keys in output order; this_file_hand is inserted here.
    samples: list of (t_ms, state, cursor_y, cursor_z, {landmark: [x, y, z]})
    with landmarks in the Liberty frame."""
    for file_hand in ('right', 'left'):
        folder = os.path.join(session_dir, hand_folder(file_hand))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f'{trial_index:04d}.csv')

        header = {}
        for key, value in meta.items():
            header[key] = value
            if key == 'used_hand':
                header['this_file_hand'] = file_hand

        is_used = (file_hand == used_hand)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            for key, value in header.items():
                f.write(f'# {key}: {_format_header_value(value)}\n')
            f.write(','.join(COLUMNS) + '\n')
            for t_ms, state, _cursor_y, _cursor_z, landmarks in samples:
                row = {'t_ms': f'{t_ms:.3f}', 'state': state}
                if is_used:
                    for lm, pos in landmarks.items():
                        if lm not in OUTPUT_JOINTS:
                            continue
                        for axis, c in zip('xyz', to_output_axes(pos)):
                            row[f'{lm}_{axis}'] = _fmt(c)
                f.write(','.join(row.get(c, '') for c in COLUMNS) + '\n')
