import sys
import os
import struct
import time
import threading
import math
from collections import deque

# ── Windows-only imports ──────────────────────────────────────────────────────
if sys.platform == 'win32':
    import socket
    import subprocess
    import atexit

# ── Linux-only imports ────────────────────────────────────────────────────────
if sys.platform != 'win32':
    try:
        import usb.core
        import usb.util
    except ImportError:
        usb = None

# ── Windows constants ─────────────────────────────────────────────────────────
UDP_PORT  = 5123
_EXE      = os.environ.get(
    'POLHEMUS_EXE',
    r'C:\Polhemus\PDI\PDI_140\Samples\bin\x64\Release\UnityExport.exe',
)
_DLL_DIRS = [
    p for p in os.environ.get(
        'POLHEMUS_DLL_DIRS',
        r'C:\Polhemus\PDI\PDI_140\Lib\x64;C:\Polhemus\PiMgr',
    ).split(';') if p
]

# ── Linux constants ───────────────────────────────────────────────────────────
_USB_VID    = 0x0f44
_USB_PID    = 0xff12
_USB_EP_OUT = 0x02
_USB_EP_IN  = 0x82
_USB_TIMEOUT = 2000  # ms


class SensorData:
    def __init__(self, x=0.0, y=0.0, z=0.0, az=0.0, el=0.0, ro=0.0):
        self.x, self.y, self.z = x, y, z
        self.az, self.el, self.ro = az, el, ro


def _quat_to_euler(qx, qy, qz, qw):
    """Polhemus quaternion -> (az, el, ro) degrees. R = Rz(az)*Ry(el)*Rx(ro)."""
    R20 = 2*(qx*qz - qy*qw)
    R21 = 2*(qy*qz + qx*qw)
    R22 = 1 - 2*(qx*qx + qy*qy)
    R10 = 2*(qx*qy + qz*qw)
    R00 = 1 - 2*(qy*qy + qz*qz)
    el  = math.degrees(math.asin(max(-1.0, min(1.0, -R20))))
    ro  = math.degrees(math.atan2(R21, R22))
    az  = math.degrees(math.atan2(R10, R00))
    return az, el, ro


class LibertyReader:
    def __init__(self, dummy=True):
        self.dummy      = dummy
        self.use_mouse  = False
        self._sensors        = {i: SensorData() for i in range(1, 5)}
        self._dummy_sensors  = {i: SensorData() for i in range(1, 5)}
        self._connected      = False
        self._last_data_time = 0.0
        self._last_sensor_time = {i: 0.0 for i in range(1, 5)}
        self._packet_times   = deque()
        self._lock           = threading.Lock()

        # Windows-only state
        self._proc             = None
        self._last_launch_time = 0.0

        # Linux-only state
        self._usb_dev = None

        if not dummy:
            if sys.platform == 'win32':
                self._launch_unity_export()
                atexit.register(self._cleanup)
            # Linux: USB init happens inside the read loop

        threading.Thread(target=self._read_loop, daemon=True).start()

    # ── Windows: process management ───────────────────────────────────────────

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
        env        = os.environ.copy()
        env['PATH'] = os.pathsep.join(_DLL_DIRS) + os.pathsep + env.get('PATH', '')
        si          = subprocess.STARTUPINFO()
        si.dwFlags  = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
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

    # ── Public API ────────────────────────────────────────────────────────────

    def get_status(self):
        """Return 'disconnected' | 'connected' | 'running'."""
        if sys.platform == 'win32':
            proc_alive = self._proc is not None and self._proc.poll() is None
            if not proc_alive:
                return 'disconnected'
            since_data = (time.perf_counter() - self._last_data_time
                          if self._last_data_time > 0 else float('inf'))
            if since_data < 1.5:
                return 'running'
            if (self._last_launch_time > self._last_data_time and
                    time.perf_counter() - self._last_launch_time < 8.0):
                return 'connected'
            return 'disconnected'
        else:
            if not self._connected:
                return 'disconnected'
            since_data = (time.perf_counter() - self._last_data_time
                          if self._last_data_time > 0 else float('inf'))
            if since_data < 1.5:
                return 'running'
            return 'connected'

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
            return 0.0 if span <= 0 else (len(self._packet_times) - 1) / span

    def get_sensor(self, n):
        with self._lock:
            src = self._dummy_sensors if self.use_mouse else self._sensors
            s   = src.get(n)
            if s is None:
                return None
            return SensorData(s.x, s.y, s.z, s.az, s.el, s.ro)

    def set_dummy_sensor(self, n, x, y, z, az=0.0, el=0.0, ro=0.0):
        with self._lock:
            self._dummy_sensors[n] = SensorData(x, y, z, az, el, ro)

    # ── Read loop dispatcher ──────────────────────────────────────────────────

    def _read_loop(self):
        if self.dummy:
            return
        if sys.platform == 'win32':
            self._windows_read_loop()
        else:
            self._linux_read_loop()

    # ── Windows read loop (UDP from UnityExport.exe) ──────────────────────────

    def _windows_read_loop(self):
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
                        self._parse_windows(data)
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

    def _parse_windows(self, data):
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
                    x, y, z    = struct.unpack_from('<3f', data, idx + 12)
                    x, y, z    = -x, -y, -z
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

    # ── Linux read loop (direct USB) ──────────────────────────────────────────

    def _usb_send(self, cmd):
        self._usb_dev.write(_USB_EP_OUT, (cmd + '\r').encode(), _USB_TIMEOUT)

    def _linux_read_loop(self):
        while True:
            try:
                self._linux_connect_and_stream()
            except Exception:
                pass
            self._connected = False
            self._usb_dev   = None
            time.sleep(2.0)

    def _linux_connect_and_stream(self):
        dev = usb.core.find(idVendor=_USB_VID, idProduct=_USB_PID)
        if dev is None:
            return

        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except usb.core.USBError:
            pass
        try:
            dev.set_configuration()
        except usb.core.USBError:
            pass
        usb.util.claim_interface(dev, 0)

        self._usb_dev   = dev
        self._connected = True

        # Stop any previous stream, set ASCII format, inches (matches Windows)
        try:
            self._usb_send('\x03')
        except Exception:
            pass
        time.sleep(0.1)
        try:
            dev.read(_USB_EP_IN, 512, 500)
        except Exception:
            pass

        self._usb_send('F0')   # standard ASCII format
        time.sleep(0.05)
        self._usb_send('U0')   # inches — matches Windows PDI SDK output
        time.sleep(0.05)
        self._usb_send('C')    # start continuous stream

        buf = ''
        while True:
            try:
                raw = dev.read(_USB_EP_IN, 512, _USB_TIMEOUT)
                buf += bytes(raw).decode('ascii', errors='replace')
            except usb.core.USBTimeoutError:
                continue

            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                self._parse_linux_frame(line)

    def _parse_linux_frame(self, line):
        """Parse one ASCII Liberty frame.

        Format: 'NN  +x.xxx  +y.yyy  +z.zzz  +az.zzz  +el.zzz  +ro.zzz'
        NN = 2-digit station (1-based), xyz in inches, angles in degrees.
        x,y,z are used as-is — the Windows PDI SDK already applies its own
        coordinate transform internally, so the raw ASCII values match.
        """
        line = line.strip()
        if len(line) < 10:
            return
        try:
            station = int(line[:2])
            if not (1 <= station <= 4):
                return
            parts = line[2:].split()
            if len(parts) < 6:
                return
            x, y, z    = float(parts[0]), float(parts[1]), float(parts[2])
            az, el, ro = float(parts[3]), float(parts[4]), float(parts[5])
            with self._lock:
                self._sensors[station] = SensorData(x, y, z, az, el, ro)
                now = time.perf_counter()
                self._last_data_time        = now
                self._last_sensor_time[station] = now
                if station == 1:
                    self._packet_times.append(now)
                    while self._packet_times and now - self._packet_times[0] > 2.0:
                        self._packet_times.popleft()
        except (ValueError, IndexError):
            pass
