import struct
import csv
import time
import os
from datetime import datetime

PIPE_NAME = r'\\.\pipe\PDIPnOPipe'
SOURCE_CSV = r'c:\Users\Jisung Yuk\Desktop\Liberty\calibration_20260505_181600.csv'

# Points to re-measure (Y, Z) in inches
REDO_POINTS = [
    (0, 14),
    (0, 18),
    (12, 18),
]

def parse_latest_frame(data):
    header = b'LY'
    last_frame = None
    i = 0
    while i < len(data) - 8:
        idx = data.find(header, i)
        if idx == -1:
            break
        frame_start = idx + 8
        if frame_start + 24 <= len(data):
            try:
                vals = struct.unpack_from('<6f', data, frame_start)
                last_frame = vals
            except:
                pass
        i = idx + 1
    return last_frame

def get_samples(pipe, n=30):
    flush_end = time.time() + 0.5
    while time.time() < flush_end:
        pipe.read(4096)
        time.sleep(0.05)

    samples = []
    buffer = b''
    deadline = time.time() + 3.0
    while len(samples) < n and time.time() < deadline:
        chunk = pipe.read(256)
        if chunk:
            buffer += chunk
            frame = parse_latest_frame(buffer)
            if frame:
                samples.append(frame)
                buffer = buffer[-64:]
        time.sleep(0.02)
    return samples

def main():
    print("=== Outlier Re-measurement ===")
    print(f"Source file: {os.path.basename(SOURCE_CSV)}")
    print("Points to re-measure:")
    for y, z in REDO_POINTS:
        print(f"  Y={y}in, Z={z}in")
    print("Commands: Enter = record | s = skip | q = quit & save\n")

    with open(SOURCE_CSV, 'r') as f:
        reader = csv.DictReader(f)
        existing_rows = list(reader)

    new_results = {}  # key: (y, z), value: row dict

    try:
        with open(PIPE_NAME, 'rb') as pipe:
            print("Liberty connected!\n")

            i = 0
            while i < len(REDO_POINTS):
                gy, gz = REDO_POINTS[i]
                already = (gy, gz) in new_results
                status = " [recorded]" if already else ""
                print(f"[{i+1}/{len(REDO_POINTS)}] Point: Y={gy}in, Z={gz}in{status}")
                cmd = input("  Place sensor and press Enter (s=skip, b=back, q=quit): ").strip().lower()

                if cmd == 'q':
                    break
                elif cmd == 'b':
                    if i > 0:
                        i -= 1
                        print(f"  -> Back to point {i+1}\n")
                    else:
                        print("  Already at first point.\n")
                    continue
                elif cmd == 's':
                    print("  Skipped.\n")
                    i += 1
                    continue

                samples = get_samples(pipe, n=30)
                if not samples:
                    print("  Failed to read data. Try again.\n")
                    continue

                avg = [sum(s[j] for s in samples) / len(samples) for j in range(6)]
                lx, ly, lz = avg[0], avg[1], avg[2]

                new_results[(gy, gz)] = {
                    'grid_y_inch': gy,
                    'grid_z_inch': gz,
                    'liberty_x_inch': round(lx, 4),
                    'liberty_y_inch': round(ly, 4),
                    'liberty_z_inch': round(lz, 4),
                    'error_y_inch': round(ly - gy, 4),
                    'error_z_inch': round(lz - gz, 4),
                }

                print(f"  Actual:  Y={gy}in, Z={gz}in")
                print(f"  Liberty: X={lx:.4f}in  Y={ly:.4f}in  Z={lz:.4f}in")
                print(f"  Error:   Y={ly - gy:+.4f}in  Z={lz - gz:+.4f}in\n")
                i += 1

    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        print(f"Error: {e}")

    if not new_results:
        print("No data recorded.")
        return

    # Replace matching rows in existing data
    redo_keys = {(gy, gz) for gy, gz in new_results}
    merged = [r for r in existing_rows
              if (int(float(r['grid_y_inch'])), int(float(r['grid_z_inch']))) not in redo_keys]
    merged += [dict((k, str(v)) for k, v in r.items()) for r in new_results.values()]
    merged.sort(key=lambda r: (float(r['grid_z_inch']), float(r['grid_y_inch'])))

    filename = f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = f"c:\\Users\\Jisung Yuk\\Desktop\\Liberty\\{filename}"
    fieldnames = ['grid_y_inch', 'grid_z_inch', 'liberty_x_inch',
                  'liberty_y_inch', 'liberty_z_inch', 'error_y_inch', 'error_z_inch']
    with open(filepath, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)

    print(f"Saved: {filename} ({len(merged)} points)")
    print(f"Re-measured: {len(new_results)} point(s)")

if __name__ == '__main__':
    main()
