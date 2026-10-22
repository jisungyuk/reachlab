"""
Quick check of reaching trial CSVs written in the shared output format
(KinematicToolBox DATA_FORMAT.md, format_version 1).

    python scripts/check_trial_files.py <session folder>
    e.g. python scripts/check_trial_files.py ~/data/P01/session_001_20261023

Per file it prints the recorded sampling rate, the spread of sample
intervals, the share of rows that repeat the previous row's coordinates,
the column count and missing header keys. Standard library only.
"""
import csv
import os
import statistics
import sys

EXPECTED_COLUMNS = 33
REQUIRED_KEYS = (
    'format_version', 'system', 'date', 'time', 'participant_id', 'session_index',
    'trial_index', 'used_hand', 'this_file_hand', 'instruction', 'target_id',
    'start_pos_cm', 'start_radius_cm', 'target_pos_cm', 'target_radius_cm',
    'hold_s', 'wait_s', 'move_s', 'feedback_s', 'ready_ms', 'go_ms', 'outcome',
    'axes', 'origin',
)


def read_trial(path):
    header, lines = {}, []
    with open(path, encoding='utf-8', newline='') as f:
        raw = f.read()
    for line in raw.split('\n'):
        if line.startswith('# '):
            key, _, value = line[2:].partition(': ')
            header[key] = value
        elif line:
            lines.append(line)
    rows = list(csv.reader(lines))
    return raw, header, rows


def check(path):
    raw, header, rows = read_trial(path)
    columns, data = rows[0], rows[1:]
    issues = []
    if raw.startswith('﻿'):
        issues.append('BOM')
    if '\r' in raw:
        issues.append('CR line endings')
    if len(columns) != EXPECTED_COLUMNS:
        issues.append(f'{len(columns)} columns')
    missing = [k for k in REQUIRED_KEYS if k not in header]
    if missing:
        issues.append('missing keys: ' + ', '.join(missing))

    coords = [c for c in columns if c.endswith(('_x', '_y', '_z'))]
    idx = [columns.index(c) for c in coords]
    has_coords = any(r[i] for r in data for i in idx)
    if not data:
        return f'{os.path.basename(path)}  no data rows  {"; ".join(issues)}'
    if not has_coords:
        return f'{os.path.basename(path)}  unused hand ({len(data)} rows, blank coordinates)  {"; ".join(issues)}'

    t = [float(r[0]) for r in data]
    dt = [b - a for a, b in zip(t, t[1:])]
    rate = (len(t) - 1) / ((t[-1] - t[0]) / 1000.0) if t[-1] > t[0] else float('nan')
    repeats = sum(1 for a, b in zip(data, data[1:]) if all(a[i] == b[i] for i in idx))
    return (f'{os.path.basename(path)}  {rate:6.1f} Hz  '
            f'dt median {statistics.median(dt):5.2f} ms (min {min(dt):5.2f}, max {max(dt):5.2f})  '
            f'repeated rows {100.0 * repeats / max(1, len(data) - 1):4.1f}%  '
            f'outcome {header.get("outcome", "?")}  {"; ".join(issues) or "format OK"}')


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        print(__doc__)
        sys.exit(1)
    session = sys.argv[1]
    for hand_folder in ('01', '02'):
        folder = os.path.join(session, hand_folder)
        if not os.path.isdir(folder):
            print(f'[{hand_folder}] missing')
            continue
        files = sorted(f for f in os.listdir(folder) if f.endswith('.csv'))
        print(f'[{hand_folder}] {len(files)} files')
        for name in files:
            print('  ' + check(os.path.join(folder, name)))


if __name__ == '__main__':
    main()
