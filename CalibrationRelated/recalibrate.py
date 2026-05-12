import struct
import csv
import time
import glob
import os
from datetime import datetime

PIPE_NAME = r'\\.\pipe\PDIPnOPipe'

Y_REDO = [28, 32]
Z_POINTS = list(range(2, 23, 4))   # 2, 6, 10, 14, 18, 22

GRID_POINTS = [(y, z) for z in Z_POINTS for y in Y_REDO]

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

def load_existing_csv():
    filepath = r'c:\Users\Jisung Yuk\Desktop\Liberty\calibration_20260505_181057.csv'
    print(f"기존 파일: {os.path.basename(filepath)}")
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return filepath, rows

def main():
    print("=== Liberty Re-calibration (Y=28, Y=32) ===")
    print(f"총 {len(GRID_POINTS)}개 포인트 재측정")
    print("s = 건너뛰기 | q = 종료 및 저장\n")

    _, existing_rows = load_existing_csv()

    new_results = []

    try:
        with open(PIPE_NAME, 'rb') as pipe:
            print("Liberty 연결됨!\n")

            for i, (gy, gz) in enumerate(GRID_POINTS):
                print(f"[{i+1}/{len(GRID_POINTS)}] 포인트: Y={gy}in, Z={gz}in")
                cmd = input("  센서 놓고 Enter (s=건너뛰기, q=종료): ").strip().lower()

                if cmd == 'q':
                    break
                if cmd == 's':
                    print("  건너뜀\n")
                    continue

                samples = get_samples(pipe, n=30)
                if not samples:
                    print("  데이터 읽기 실패. 건너뜀\n")
                    continue

                avg = [sum(s[j] for s in samples) / len(samples) for j in range(6)]
                lx, ly, lz = avg[0], avg[1], avg[2]

                new_results.append({
                    'grid_y_inch': gy,
                    'grid_z_inch': gz,
                    'liberty_x_inch': round(lx, 4),
                    'liberty_y_inch': round(ly, 4),
                    'liberty_z_inch': round(lz, 4),
                    'error_y_inch': round(ly - gy, 4),
                    'error_z_inch': round(lz - gz, 4),
                })

                print(f"  실제:    Y={gy}in, Z={gz}in")
                print(f"  Liberty: Y={ly:.4f}in, Z={lz:.4f}in")
                print(f"  오차:    Y={ly - gy:+.4f}in  Z={lz - gz:+.4f}in\n")

    except KeyboardInterrupt:
        print("\n중단됨.")
    except Exception as e:
        print(f"오류: {e}")

    if not new_results:
        print("측정된 데이터 없음.")
        return

    # 기존 rows에서 Y=28, Y=32 제거하고 새 데이터로 교체
    merged = [r for r in existing_rows
              if int(float(r['grid_y_inch'])) not in Y_REDO]
    merged += [dict((k, str(v)) for k, v in r.items()) for r in new_results]

    # grid_y, grid_z 기준으로 정렬
    merged.sort(key=lambda r: (float(r['grid_z_inch']), float(r['grid_y_inch'])))

    filename = f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = f"c:\\Users\\Jisung Yuk\\Desktop\\Liberty\\{filename}"
    with open(filepath, 'w', newline='') as f:
        fieldnames = ['grid_y_inch', 'grid_z_inch', 'liberty_x_inch',
                      'liberty_y_inch', 'liberty_z_inch', 'error_y_inch', 'error_z_inch']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)

    print(f"저장됨: {filename} (총 {len(merged)}개 포인트)")

if __name__ == '__main__':
    main()
