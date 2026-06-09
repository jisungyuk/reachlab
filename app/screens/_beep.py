"""Cross-platform beep utility. Uses winsound on Windows, aplay on Linux."""
import sys

if sys.platform == 'win32':
    import winsound as _winsound
    def beep(freq=880, dur=120):
        _winsound.Beep(freq, dur)
else:
    import io, math, struct, subprocess, wave
    def beep(freq=880, dur=120):
        rate     = 44100
        n        = int(rate * dur / 1000)
        samples  = [int(32767 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)]
        buf      = struct.pack('<' + 'h' * n, *samples)
        wav_io   = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(buf)
        proc = subprocess.Popen(
            ['aplay', '-q', '-'],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc.communicate(wav_io.getvalue())
