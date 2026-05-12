import struct
import csv
import time
from datetime import datetime

PIPE_NAME = r'\\.\pipe\PDIPnOPipe'

# Grid definition: 22 x 34 inches, 4-inch spacing
# Liberty axes: Y = left/right, Z = front/back
Y_POINTS = list(range(0, 35, 4))
Z_POINTS = list(range(2, 23, 4))

GRID_POINTS = [(y, z) for z in Z_POINTS for y in Y_POINTS]

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
    print("=== Liberty Calibration Tool ===")
    print(f"Total {len(GRID_POINTS)} points (4-inch spacing, 34x22 inches)")
    print("Commands: Enter = record | s = skip | b = go back | q = quit & save\n")

    results = {}  # key: index, value: dict

    try:
        with open(PIPE_NAME, 'rb') as pipe:
            print("Liberty connected!\n")

            i = 0
            while i < len(GRID_POINTS):
                gy, gz = GRID_POINTS[i]
                already = i in results
                status = " [recorded]" if already else ""
                print(f"[{i+1}/{len(GRID_POINTS)}] Point: Y={gy}in, Z={gz}in{status}")
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

                results[i] = {
                    'grid_y_inch': gy,
                    'grid_z_inch': gz,
                    'liberty_x_inch': round(lx, 4),
                    'liberty_y_inch': round(ly, 4),
                    'liberty_z_inch': round(lz, 4),
                    'error_y_inch': round(ly - gy, 4),
                    'error_z_inch': round(lz - gz, 4),
                }

                print(f"  Actual:  Y={gy}in, Z={gz}in")
                print(f"  Liberty: Y={ly:.4f}in, Z={lz:.4f}in")
                print(f"  Error:   Y={ly - gy:+.4f}in  Z={lz - gz:+.4f}in\n")
                i += 1

    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        print(f"Error: {e}")

    if results:
        rows = [results[k] for k in sorted(results.keys())]
        filename = f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = f"c:\\Users\\Jisung Yuk\\Desktop\\Liberty\\{filename}"
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved: {filename} ({len(rows)} points)")

if __name__ == '__main__':
    main()
