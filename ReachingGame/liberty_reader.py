import struct
import time
import threading
import socket
import subprocess
import os
import atexit
import math
from collections import deque

UDP_PORT = 5123

_EXE = r'C:\Polhemus\PDI\PDI_140\Samples\bin\x64\Release\UnityExport.exe'
_DLL_DIRS = [
    r'C:\Polhemus\PDI\PDI_140\Lib\x64',
    r'C:\Polhemus\PiMgr',
]


class SensorData:
    def __init__(self, x=0.0, y=0.0, z=0.0, az=0.0, el=0.0, ro=0.0):
        self.x, self.y, self.z = x, y, z
        self.az, self.el, self.ro = az, el, ro


def _quat_to_euler(qx, qy, qz, qw):
    """Polhemus quaternion (qx,qy,qz,qw) -> (az,el,ro) degrees. R = Rz(az)*Ry(el)*Rx(ro)."""
    R20 = 2*(qx*qz - qy*qw)
    R21 = 2*(qy*qz + qx*qw)
    R22 = 1 - 2*(qx*qx + qy*qy)
    R10 = 2*(qx*qy + qz*qw)
    R00 = 1 - 2*(qy*qy + qz*qz)
    el = math.degrees(math.asin(max(-1.0, min(1.0, -R20))))
    ro = math.degrees(math.atan2(R21, R22))
    az = math.degrees(math.atan2(R10, R00))
    return az, el, ro


class LibertyReader:
    def __init__(self, dummy=True):
        self.dummy = dummy
        self.use_mouse = False
        self._sensors = {i: SensorData() for i in range(1, 5)}
        self._dummy_sensors = {i: SensorData() for i in range(1, 5)}
        self._connected = False
        self._last_data_time = 0.0
        self._last_sensor_time = {i: 0.0 for i in range(1, 5)}
        self._packet_times = deque()
        self._lock = threading.Lock()
        self._proc = None
        self._last_launch_time = 0.0
        if not dummy:
            self._launch_unity_export()
            atexit.register(self._cleanup)
        threading.Thread(target=self._read_loop, daemon=True).start()

    @staticmethod
    def _kill_all_unity_export():
        try:
            subprocess.call(
                ['taskkill', '/F', '/IM', 'UnityExport.exe'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _launch_unity_export(self):
        if not os.path.exists(_EXE):
            return
        env = os.environ.copy()
        env['PATH'] = ';'.join(_DLL_DIRS) + ';' + env.get('PATH', '')
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        try:
            self._proc = subprocess.Popen(
                [_EXE],
                startupinfo=si,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                env=env,
            )
            self._last_launch_time = time.perf_counter()
        except Exception:
            self._proc = None

    def _cleanup(self):
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def _restart_unity_export(self):
        if time.perf_counter() - self._last_launch_time < 8.0:
            return
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
            try:
                self._proc.wait(timeout=2.0)
            except Exception:
                pass
        self._kill_all_unity_export()
        time.sleep(5.0)
        self._launch_unity_export()

    def get_status(self):
        """Return 'disconnected' | 'connected' | 'running'."""
        proc_alive = self._proc is not None and self._proc.poll() is None
        if not proc_alive:
            return 'disconnected'
        since_data = (time.perf_counter() - self._last_data_time
                      if self._last_data_time > 0 else float('inf'))
        if since_data < 1.5:
            return 'running'
        # CONNECTED: just launched/restarted, waiting for Liberty to stream
        if (self._last_launch_time > self._last_data_time and
                time.perf_counter() - self._last_launch_time < 8.0):
            return 'connected'
        return 'disconnected'

    def is_connected(self):
        return self._connected

    def is_running(self):
        return self._connected and (time.perf_counter() - self._last_data_time < 1.5)

    def is_sensor_active(self, n):
        return time.perf_counter() - self._last_sensor_time.get(n, 0.0) < 1.5

    def get_read_rate(self):
        with self._lock:
            if len(self._packet_times) < 2:
                return 0.0
            span = self._packet_times[-1] - self._packet_times[0]
            if span <= 0:
                return 0.0
            return (len(self._packet_times) - 1) / span

    def get_sensor(self, n):
        with self._lock:
            src = self._dummy_sensors if self.use_mouse else self._sensors
            s = src.get(n)
            if s is None:
                return None
            return SensorData(s.x, s.y, s.z, s.az, s.el, s.ro)

    def set_dummy_sensor(self, n, x, y, z, az=0.0, el=0.0, ro=0.0):
        with self._lock:
            self._dummy_sensors[n] = SensorData(x, y, z, az, el, ro)

    def _read_loop(self):
        if self.dummy:
            return
        while True:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('', UDP_PORT))
                sock.settimeout(2.0)
                self._connected = True
                while True:
                    try:
                        data, _ = sock.recvfrom(4096)
                        self._parse(data)
                    except socket.timeout:
                        if self._proc and self._proc.poll() is not None:
                            self._restart_unity_export()
                        continue
            except Exception:
                self._connected = False
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
            time.sleep(1.0)

    def _parse(self, data):
        i = 0
        while i < len(data) - 40:
            idx = data.find(b'LY', i)
            if idx == -1:
                break
            if idx + 40 > len(data):
                break
            try:
                station = data[idx + 2]
                if 1 <= station <= 4:
                    x, y, z = struct.unpack_from('<3f', data, idx + 12)
                    x, y, z = -x, -y, -z
                    qx, qy, qz, qw = struct.unpack_from('<4f', data, idx + 24)
                    az, el, ro = _quat_to_euler(qx, qy, qz, qw)
                    with self._lock:
                        self._sensors[station] = SensorData(x, y, z, az, el, ro)
                        now = time.perf_counter()
                        self._last_data_time = now
                        self._last_sensor_time[station] = now
                        if station == 1:
                            self._packet_times.append(now)
                            while self._packet_times and now - self._packet_times[0] > 2.0:
                                self._packet_times.popleft()
            except Exception:
                pass
            i = idx + 1
