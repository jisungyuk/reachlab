import math


def rotation_matrix(az_deg, el_deg, ro_deg):
    """Polhemus Euler angles (degrees) -> 3x3 rotation matrix.
    Convention: R = Rz(az) @ Ry(el) @ Rx(ro)
    """
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    ro = math.radians(ro_deg)
    caz, saz = math.cos(az), math.sin(az)
    cel, sel = math.cos(el), math.sin(el)
    cro, sro = math.cos(ro), math.sin(ro)
    return [
        [caz*cel,  caz*sel*sro - saz*cro,  caz*sel*cro + saz*sro],
        [saz*cel,  saz*sel*sro + caz*cro,  saz*sel*cro - caz*sro],
        [-sel,     cel*sro,                cel*cro               ],
    ]


def _mat_T(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def _mat_vec(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def compute_offset(hand_s, pointer_s):
    """Compute MCP offset in hand sensor's local frame.

    hand_s    : SensorData  (x,y,z inches; az,el,ro degrees)
    pointer_s : SensorData  (x,y,z inches; orientation ignored)
    Returns   : [x, y, z] offset in cm (local frame of hand_s)
    """
    ph   = [hand_s.x    * 2.54, hand_s.y    * 2.54, hand_s.z    * 2.54]
    pp   = [pointer_s.x * 2.54, pointer_s.y * 2.54, pointer_s.z * 2.54]
    diff = [pp[i] - ph[i] for i in range(3)]
    R    = rotation_matrix(hand_s.az, hand_s.el, hand_s.ro)
    return _mat_vec(_mat_T(R), diff)


def finalize_forearm(hand_s, forearm_s, offsets_hand):
    """Convert landmark offsets from hand-sensor frame to forearm-sensor frame.

    hand_s       : SensorData of hand sensor (current reading)
    forearm_s    : SensorData of forearm sensor (just placed, current reading)
    offsets_hand : {name: [x,y,z]} stored in hand sensor's local frame
    Returns      : {name: [x,y,z]} in forearm sensor's local frame
    """
    R_h    = rotation_matrix(hand_s.az,    hand_s.el,    hand_s.ro)
    R_f_T  = _mat_T(rotation_matrix(forearm_s.az, forearm_s.el, forearm_s.ro))
    ph     = [hand_s.x    * 2.54, hand_s.y    * 2.54, hand_s.z    * 2.54]
    pf     = [forearm_s.x * 2.54, forearm_s.y * 2.54, forearm_s.z * 2.54]
    result = {}
    for name, off_h in offsets_hand.items():
        p_world = [ph[i] + _mat_vec(R_h, off_h)[i] for i in range(3)]
        result[name] = _mat_vec(R_f_T, [p_world[i] - pf[i] for i in range(3)])
    return result


def track_mcp(hand_s, offset_local):
    """Compute world position of MCP given current hand sensor and stored local offset.

    Returns [x, y, z] in cm (raw sensor-frame, before desk-origin offset).
    """
    ph           = [hand_s.x * 2.54, hand_s.y * 2.54, hand_s.z * 2.54]
    R            = rotation_matrix(hand_s.az, hand_s.el, hand_s.ro)
    offset_world = _mat_vec(R, offset_local)
    return [ph[i] + offset_world[i] for i in range(3)]
