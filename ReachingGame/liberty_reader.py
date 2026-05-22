import struct
import time
import threading
from collections import deque

PIPE_NAME = r'\\.\pipe\PDIPnOPipe'


class SensorData:
    def __init__(self, x=0.0, y=0.0, z=0.0, az=0.0, el=0.0, ro=0.0):
        self.x, self.y, self.z = x, y, z
        self.az, self.el, self.ro = az, el, ro


class LibertyReader:
    def __init__(self, dummy=True):
        self.dummy = dummy
        self.use_mouse = False
        self._sensors = {i: SensorData() for i in range(1, 5)}
        self._dummy_sensors = {i: SensorData() for i in range(1, 5)}
        self._connected = False
        self._last_data_time = 0.0
        self._last_sensor_time = {i: 0.0 for i in range(1, 5)}
        self._packet_times = deque()   # timestamps of recent packets for rate estimation
        self._lock = threading.Lock()
        threading.Thread(target=self._read_loop, daemon=True).start()

    def is_connected(self):
        return self._connected

    def is_running(self):
        return self._connected and (time.perf_counter() - self._last_data_time < 1.5)

    def is_sensor_active(self, n):
        return time.perf_counter() - self._last_sensor_time.get(n, 0.0) < 1.5

    def get_read_rate(self):
        """Return estimated packets/sec over the last 2 seconds."""
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
        while True:
            try:
                with open(PIPE_NAME, 'rb') as pipe:
                    self._connected = True
                    buffer = b''
                    while True:
                        chunk = pipe.read(512)
                        if not chunk:
                            continue
                        buffer += chunk
                        self._parse(buffer)
                        buffer = buffer[-128:]
            except Exception:
                self._connected = False
                time.sleep(1.0)

    def _parse(self, data):
        header = b'LY'
        i = 0
        while i < len(data) - 32:
            idx = data.find(header, i)
            if idx == -1:
                break
            if idx + 32 <= len(data):
                try:
                    station = data[idx + 2]
                    if 1 <= station <= 4:
                        vals = struct.unpack_from('<6f', data, idx + 8)
                        with self._lock:
                            self._sensors[station] = SensorData(*vals)
                            now = time.perf_counter()
                            self._last_data_time = now
                            self._last_sensor_time[station] = now
                            if station == 1:  # track rate via one station only
                                self._packet_times.append(now)
                                while self._packet_times and now - self._packet_times[0] > 2.0:
                                    self._packet_times.popleft()
                except Exception:
                    pass
            i = idx + 1
