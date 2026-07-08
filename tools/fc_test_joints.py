"""验证 Sesame-Micro.FCStd 的关节:扰动左前腿 -> solve -> 检查约束咬合与机身固定。

只读验证(不回存文件)。freecadcmd 运行,ASCII 输出。
"""
import json
import math
import os

import FreeCAD
import UtilsAssembly

REPO = "/home/lxy/Desktop/work/sesame-robot-micro"
doc = FreeCAD.openDocument(os.path.join(REPO, "hardware", "CAD", "Sesame-Micro.FCStd"))
structure = json.load(open(os.path.join(REPO, "simulation", "fusion_export", "structure.json")))

asm = next(o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject")
joints = [o for o in doc.Objects if hasattr(o, "JointType") and o.JointType == "Revolute"]
link = {o.Label: o for o in asm.Group if o.TypeId == "App::Part"}
grounded = next(o for o in doc.Objects if hasattr(o, "ObjectToGround"))
link["body"] = grounded.ObjectToGround
print("joints:", len(joints), "links:", sorted(link))

V = FreeCAD.Vector


def coincidence():
    worst_pos, worst_ax, worst_name = 0.0, 0.0, ""
    for j in joints:
        p1 = UtilsAssembly.getJcsGlobalPlc(j.Placement1, j.Reference1)
        p2 = UtilsAssembly.getJcsGlobalPlc(j.Placement2, j.Reference2)
        dp = (p1.Base - p2.Base).Length
        z1, z2 = p1.Rotation.multVec(V(0, 0, 1)), p2.Rotation.multVec(V(0, 0, 1))
        da = math.degrees(math.acos(max(-1.0, min(1.0, z1.dot(z2)))))
        if dp > worst_pos or da > worst_ax:
            worst_pos, worst_ax, worst_name = max(dp, worst_pos), max(da, worst_ax), j.Name
    return worst_pos, worst_ax, worst_name


wp, wa, wn = coincidence()
print("initial coincidence: worst_pos=%.6f mm worst_axis=%.6f deg (%s)" % (wp, wa, wn))

# ---- 扰动左前腿 ----
hip = next(j for j in structure["joints"] if j["name"] == "hip_lf_rev")
o, ax = hip["originWorld"], hip["axisWorld"]
origin = V(o[0] * 10, o[1] * 10, o[2] * 10)
axis = V(ax[0], ax[1], ax[2])

rot = FreeCAD.Placement(origin, FreeCAD.Rotation(axis, 25.0), V(0, 0, 0)) \
    if False else FreeCAD.Placement()
# 绕世界系中过 origin 的 axis 转 25 度:P' = T(o) * R * T(-o) * P
R = FreeCAD.Placement(V(0, 0, 0), FreeCAD.Rotation(axis, 25.0))
To = FreeCAD.Placement(origin, FreeCAD.Rotation())
Tno = FreeCAD.Placement(-origin, FreeCAD.Rotation())
upper, lower, body = link["upper_lf"], link["lower_lf"], link["body"]
body_before = FreeCAD.Placement(body.Placement)
foot_before = FreeCAD.Placement(lower.Placement)

upper.Placement = To * R * Tno * upper.Placement
lower.Placement = FreeCAD.Placement(
    lower.Placement.Base + V(8, 3, -5), lower.Placement.Rotation)
doc.recompute()
wp, wa, wn = coincidence()
print("after perturb: worst_pos=%.3f mm worst_axis=%.3f deg (%s)" % (wp, wa, wn))

rc = asm.solve(False)
doc.recompute()
wp, wa, wn = coincidence()
print("after solve rc=%s: worst_pos=%.6f mm worst_axis=%.6f deg (%s)" % (rc, wp, wa, wn))

body_moved = (body.Placement.Base - body_before.Base).Length
lower_moved = (lower.Placement.Base - foot_before.Base).Length
print("body moved %.6f mm (expect 0), lower_lf moved %.3f mm vs zero pose (expect >0, leg rotated)"
      % (body_moved, lower_moved))
ok = wp < 1e-3 and wa < 1e-3 and body_moved < 1e-6 and lower_moved > 1.0
print("RESULT:", "PASS" if ok else "FAIL")
