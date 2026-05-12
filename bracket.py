import numpy as np
from stl import mesh

def box_to_triangles(x_min, x_max, y_min, y_max, z_min, z_max):
    v = np.array([
        [x_min, y_min, z_min], [x_max, y_min, z_min],
        [x_max, y_max, z_min], [x_min, y_max, z_min],
        [x_min, y_min, z_max], [x_max, y_min, z_max],
        [x_max, y_max, z_max], [x_min, y_max, z_max],
    ])
    f = np.array([
        [0,1,2],[0,2,3],
        [4,5,6],[4,6,7],
        [0,1,5],[0,5,4],
        [2,3,7],[2,7,6],
        [1,2,6],[1,6,5],
        [0,3,7],[0,7,4],
    ])
    return np.array([[v[f[i][0]], v[f[i][1]], v[f[i][2]]] for i in range(len(f))])

# Dimensions (mm)
thickness = 4.0
vertical_w = 75.0    # vertical face width (X)
vertical_h = 75.0    # vertical face height (Z)
horizontal_w = 75.0  # horizontal face width (X)
horizontal_d = 90.0  # horizontal face depth (Y)

# Cable tie slot dimensions
slot_w = 35.0   # 3.5cm wide
slot_h = 2.0    # 0.2cm tall
slot_margin_from_top = 8.0  # distance from top of vertical face

slot_x_min = (vertical_w - slot_w) / 2
slot_x_max = slot_x_min + slot_w
slot_z_max = vertical_h - slot_margin_from_top
slot_z_min = slot_z_max - slot_h

# Vertical face split into 3 sections to create slot opening:
# Section 1: below slot
vert_bottom = box_to_triangles(0, vertical_w, 0, thickness, 0, slot_z_min)
# Section 2: above slot
vert_top = box_to_triangles(0, vertical_w, 0, thickness, slot_z_max, vertical_h)
# Section 3: left of slot (middle height)
vert_left = box_to_triangles(0, slot_x_min, 0, thickness, slot_z_min, slot_z_max)
# Section 4: right of slot (middle height)
vert_right = box_to_triangles(slot_x_max, vertical_w, 0, thickness, slot_z_min, slot_z_max)

# Horizontal face
horiz = box_to_triangles(0, horizontal_w, thickness, thickness + horizontal_d,
                         vertical_h - thickness, vertical_h)

# Support ledge: 6cm below slot, left 4cm only, extends 4cm inward (Y direction)
support_w = 40.0   # 4cm wide (left side only)
support_d = 40.0   # 4cm deep (inward)
support_thickness = 4.0
support_z_top = slot_z_min - 60.0
support_z_bottom = support_z_top - support_thickness

support = box_to_triangles(0, support_w,
                           0, thickness + support_d,
                           support_z_bottom, support_z_top)

all_tris = np.vstack([vert_bottom, vert_top, vert_left, vert_right, horiz, support])

bracket = mesh.Mesh(np.zeros(len(all_tris), dtype=mesh.Mesh.dtype))
for i, tri in enumerate(all_tris):
    bracket.vectors[i] = tri

bracket.save('c:\\Users\\Jisung Yuk\\Desktop\\Liberty\\polhemus_bracket.stl')
print("STL saved: polhemus_bracket.stl")
print(f"Vertical face: {vertical_w}mm x {vertical_h}mm")
print(f"Horizontal face: {horizontal_w}mm x {horizontal_d}mm")
print(f"Thickness: {thickness}mm")
print(f"Cable tie slot: {slot_w}mm x {slot_h}mm, {slot_margin_from_top}mm from top")
print(f"Support ledge: {support_w}mm wide x {support_d}mm deep, top at Z={support_z_top}mm")
