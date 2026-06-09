import struct

PIPE_NAME = r'\\.\pipe\PDIPnOPipe'

def parse_frame(data):
    header = b'LY'
    frames = []
    i = 0
    while i < len(data) - 8:
        idx = data.find(header, i)
        if idx == -1:
            break
        frame_start = idx + 8
        if frame_start + 24 <= len(data):
            try:
                header_bytes = data[idx:idx+8]
                vals = struct.unpack_from('<6f', data, frame_start)
                frames.append((header_bytes, vals))
            except:
                pass
        i = idx + 1
    return frames

def read_liberty():
    print(f"Connecting to {PIPE_NAME}...")
    try:
        with open(PIPE_NAME, 'rb') as pipe:
            print("Connected! Reading data (Ctrl+C to stop)...\n")
            print(f"{'X':>10} {'Y':>10} {'Z':>10} {'Az':>10} {'El':>10} {'Ro':>10}")
            print("-" * 65)
            buffer = b''
            while True:
                chunk = pipe.read(512)
                if not chunk:
                    continue
                buffer += chunk
                frames = parse_frame(buffer)
                if frames:
                    hdr, vals = frames[0]
                    print(f"Header bytes (hex): {hdr.hex()}")
                    for i, b in enumerate(hdr):
                        print(f"  byte[{i}] = {b}")
                    x, y, z, az, el, ro = vals
                    print(f"\nFirst frame values:")
                    print(f"  X={x:.3f}  Y={y:.3f}  Z={z:.3f}")
                    return
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Error: {e}")

read_liberty()
