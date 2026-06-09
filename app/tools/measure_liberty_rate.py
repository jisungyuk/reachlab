"""
Measures the actual Liberty sensor update rate via UDP (UnityExport).
Launches UnityExport.exe automatically, measures for DURATION seconds,
then prints mean Hz, std dev, min/max interval per station.
"""

import socket
import struct
import time
import statistics
import subprocess
import os
import atexit

UDP_PORT = 5123
DURATION = 30.0
HEADER   = b'LY'

_EXE = os.environ.get(
    'POLHEMUS_EXE',
    r'C:\Polhemus\PDI\PDI_140\Samples\bin\x64\Release\UnityExport.exe',
)
_DLL_DIRS = [
    p for p in os.environ.get(
        'POLHEMUS_DLL_DIRS',
        r'C:\Polhemus\PDI\PDI_140\Lib\x64;C:\Polhemus\PiMgr',
    ).split(';') if p
]

_proc = None


def _launch():
    global _proc
    if not os.path.exists(_EXE):
        print(f"ERROR: UnityExport.exe not found at {_EXE}")
        return False
    env = os.environ.copy()
    env['PATH'] = os.pathsep.join(_DLL_DIRS) + os.pathsep + env.get('PATH', '')
    si = subprocess.STARTUPINFO()
    si.dwFlags = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    _proc = subprocess.Popen(
        [_EXE],
        startupinfo=si,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        env=env,
    )
    atexit.register(_cleanup)
    print(f"Launched UnityExport.exe (pid {_proc.pid})")
    return True


def _cleanup():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.kill()
        print("UnityExport.exe stopped.")


def measure():
    if not _launch():
        return

    print("Waiting 3s for Liberty to connect...")
    time.sleep(3.0)

    if _proc.poll() is not None:
        print(f"ERROR: UnityExport.exe exited early (code {_proc.returncode})")
        return

    print(f"Listening on UDP port {UDP_PORT}")
    print(f"Measuring for {DURATION} seconds — keep sensors active...\n")

    timestamps = {i: [] for i in range(1, 5)}

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', UDP_PORT))
        sock.settimeout(2.0)
    except Exception as e:
        print(f"ERROR binding socket: {e}")
        return

    start = time.perf_counter()
    try:
        while time.perf_counter() - start < DURATION:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue

            now = time.perf_counter()
            i = 0
            while i < len(data) - 40:
                idx = data.find(HEADER, i)
                if idx == -1:
                    break
                if idx + 40 > len(data):
                    break
                try:
                    station = data[idx + 2]
                    if 1 <= station <= 4:
                        timestamps[station].append(now)
                except Exception:
                    pass
                i = idx + 1

    except KeyboardInterrupt:
        pass
    finally:
        sock.close()

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
