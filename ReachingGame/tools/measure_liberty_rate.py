"""
Measures the actual Liberty sensor update rate.
Run this script while Liberty is connected and streaming.
Records packet arrival timestamps for each station over DURATION seconds,
then prints mean Hz, std dev, min/max interval per station.
"""

import struct
import time
import statistics

PIPE_NAME = r'\\.\pipe\PDIPnOPipe'
DURATION  = 30.0   # seconds to measure
HEADER    = b'LY'


def measure():
    print(f"Connecting to Liberty pipe: {PIPE_NAME}")
    print(f"Measuring for {DURATION} seconds — keep sensors active...\n")

    timestamps = {i: [] for i in range(1, 5)}
    start = None

    try:
        with open(PIPE_NAME, 'rb') as pipe:
            print("Connected. Recording...")
            buffer = b''
            start  = time.perf_counter()

            while time.perf_counter() - start < DURATION:
                chunk = pipe.read(512)
                if not chunk:
                    continue
                buffer += chunk
                now = time.perf_counter()

                i = 0
                while i < len(buffer) - 32:
                    idx = buffer.find(HEADER, i)
                    if idx == -1:
                        break
                    if idx + 32 <= len(buffer):
                        try:
                            station = buffer[idx + 2]
                            if 1 <= station <= 4:
                                timestamps[station].append(now)
                        except Exception:
                            pass
                    i = idx + 1

                buffer = buffer[-128:]

    except FileNotFoundError:
        print("ERROR: Liberty pipe not found. Is the Liberty software running?")
        return
    except Exception as ex:
        print(f"ERROR: {ex}")
        return

    elapsed = time.perf_counter() - start
    print(f"\nMeasured for {elapsed:.1f}s\n")
    print(f"{'Station':<10} {'Packets':>8} {'Mean Hz':>10} {'Std (ms)':>10} {'Min (ms)':>10} {'Max (ms)':>10}")
    print("-" * 62)

    for station, ts in timestamps.items():
        if len(ts) < 2:
            print(f"{station:<10} {'(no data)':>8}")
            continue

        intervals_ms = [(ts[k] - ts[k-1]) * 1000 for k in range(1, len(ts))]
        mean_int = statistics.mean(intervals_ms)
        mean_hz  = 1000.0 / mean_int if mean_int > 0 else 0
        std_ms   = statistics.stdev(intervals_ms) if len(intervals_ms) > 1 else 0
        min_ms   = min(intervals_ms)
        max_ms   = max(intervals_ms)

        print(f"{station:<10} {len(ts):>8} {mean_hz:>10.1f} {std_ms:>10.2f} {min_ms:>10.2f} {max_ms:>10.2f}")

    print()


if __name__ == '__main__':
    measure()
