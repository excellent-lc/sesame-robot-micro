"""从 modbot.step + structure.json + links.json 构建带关节的 FreeCAD 装配。

用 freecadcmd 跑。输出纯 ASCII。
产物: hardware/CAD/Sesame-Micro.FCStd
"""
import json
import math
import os

import FreeCAD
import Import

REPO = "/home/lxy/Desktop/work/sesame-robot-micro"
EXP = os.path.join(REPO, "simulation", "fusion_export")
OUT = os.path.join(REPO, "hardware", "CAD", "Sesame-Micro.FCStd")

structure = json.load(open(os.path.join(EXP, "structure.json")))
links = json.load(open(os.path.join(EXP, "links.json")))

# 关节创建时不自动求解,最后统一 solve
FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly").SetBool(
    "SolveInJointCreation", False)

V = FreeCAD.Vector
ROT = FreeCAD.Rotation
PLC = FreeCAD.Placement


def occ_translation_mm(occ_path):
    t = structure["occs"][occ_path]["transform"]
    return V(t[3] * 10, t[7] * 10, t[11] * 10)


# ---------------- stage 1: import ----------------
doc = FreeCAD.newDocument("SesameMicro")
Import.insert(os.path.join(EXP, "modbot.step"), "SesameMicro")
root = [o for o in doc.Objects if not o.InList and o.TypeId == "App::Part"][0]
tops = list(root.Group)
print("stage1 import ok, root:", root.Label.encode("ascii", "replace").decode(),
      "tops:", len(tops))

# ---------------- stage 2: map STEP tops -> Fusion occs ----------------
fusion_tops = sorted({p.split("+")[0] for p in structure["occs"]})
servo_occs = [t for t in fusion_tops if t.startswith("DM-S0020")]
name_map = {}   # fusion top occ -> freecad object
PREFIX = [("SPDT", "SPDT Mini Slide Switch:1"),
          ("Seeed Studio XIAO", "Seeed Studio XIAO-ESP32-C3:1"),
          ("Waveshare", "Waveshare 1315 0.49in i2c 64x32 oled display v1:1"),
          ("proto-board", "proto-board:1"),
          ("hip_lf", "hip_lf:1"), ("hip_lr", "hip_lr:1"),
          ("hip_rf", "hip_rf:1"), ("hip_rr", "hip_rr:1"),
          ("F-L3", "F-L3:1"), ("F-L4", "F-L4:1"),
          ("F-R3", "F-R3:1"), ("F-R4", "F-R4:1"),
          # Fusion 根组件散装 body(机身框架板),STEP 导出打包成 COMPOUND
          ("COMPOUND", "COMPOUND:root")]

unmatched = []
for obj in tops:
    lab = obj.Label
    if lab.startswith("DM-S0020"):
        # 用平移量匹配是哪台舵机
        best, bestd = None, 1e9
        for occ in servo_occs:
            d = (obj.Placement.Base - occ_translation_mm(occ)).Length
            if d < bestd:
                best, bestd = occ, d
        if bestd > 0.1:
            unmatched.append((lab, "servo dist %.3f" % bestd))
            continue
        assert best not in name_map, "duplicate servo match " + best
        name_map[best] = obj
    else:
        for pref, occ in PREFIX:
            if lab.startswith(pref):
                name_map[occ] = obj
                break
        else:
            unmatched.append((lab, "no prefix rule"))

print("stage2 matched:", len(name_map), ", unmatched:",
      [u[0].encode("ascii", "replace").decode() + " " + u[1] for u in unmatched])
assert len(name_map) >= 20 and not unmatched, "top mapping incomplete"
if "COMPOUND:root" in name_map:
    links["body"].append("COMPOUND:root")

# ---------------- stage 3: split servos into body/arm features ----------------
servo_feat = {}   # 'S3.body' -> (feature obj, global placement)
for occ, part in name_map.items():
    if not occ.startswith("DM-S0020"):
        continue
    n = occ.split(":")[1]
    feats = [c for c in part.Group if c.TypeId == "Part::Feature"]
    body = [f for f in feats if "arm" not in f.Label.lower()]
    arm = [f for f in feats if "arm" in f.Label.lower()]
    assert len(body) == 1 and len(arm) == 1, \
        "servo %s features: %s" % (occ, [f.Label for f in feats])
    for key, f in (("S%s.body" % n, body[0]), ("S%s.arm" % n, arm[0])):
        f.Label = key.replace(".", "_")   # 先改名,防止 "body" 和链标签冲突
        servo_feat[key] = (f, part.Placement * f.Placement)
print("stage3 servo features split:", len(servo_feat))

# ---------------- stage 4: assembly + link containers ----------------
asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
jg = doc.addObject("Assembly::JointGroup", "Joints")
asm.addObject(jg)

link_obj = {}
for lname, members in links.items():
    lp = doc.addObject("App::Part", "link_" + lname)
    lp.Label = lname
    asm.addObject(lp)
    link_obj[lname] = lp
    for m in members:
        if m in servo_feat:
            f, gplc = servo_feat[m]
            lp.addObject(f)
            f.Placement = gplc
        else:
            lp.addObject(name_map[m])

# 清理空壳:舵机容器和 STEP 根容器(其 Origin 一并删)
def purge(obj):
    kids = [c for c in obj.OutList if c.TypeId.startswith("App::Origin")
            or c.TypeId in ("App::Line", "App::Plane", "App::Point")]
    doc.removeObject(obj.Name)
    for k in kids:
        try:
            doc.removeObject(k.Name)
        except Exception:
            pass

for occ in servo_occs:
    purge(name_map[occ])
purge(root)
doc.recompute()
labels = sorted(lp.Label for lp in link_obj.values())
print("stage4 links built:", labels)
assert labels == sorted(links), "link label collision: %s" % labels

# ---------------- stage 5: joints ----------------
import JointObject

node_link = {}
for lname, members in links.items():
    for m in members:
        node_link[m] = lname


def node(path):
    top = path.split("+")[0]
    if top.startswith("DM-S0020"):
        n = top.split(":")[1]
        return "S%s.arm" % n if "arm_double" in path else "S%s.body" % n
    return top


ground = doc.addObject("App::FeaturePython", "GroundedJoint")
jg.addObject(ground)
JointObject.GroundedJoint(ground, link_obj["body"])

made = []
for j in structure["joints"]:
    if j["type"] != "revolute":
        continue
    l1, l2 = node_link[node(j["occ1"])], node_link[node(j["occ2"])]
    o = j["originWorld"]
    ax = j["axisWorld"]
    world = PLC(V(o[0] * 10, o[1] * 10, o[2] * 10),
                ROT(V(0, 0, 1), V(ax[0], ax[1], ax[2])))
    jt = doc.addObject("App::FeaturePython", j["name"])
    jg.addObject(jt)                  # 必须先入组,Joint.__init__ 要找所属装配
    JointObject.Joint(jt, 1)          # 1 = Revolute
    jt.Detach1 = True
    jt.Detach2 = True
    jt.Placement1 = world
    jt.Placement2 = world
    # 双空子路径:migrationScript4 在文档恢复时会取 ref[1][0] 和 ref[1][1]
    jt.Reference1 = (link_obj[l1], ["", ""])
    jt.Reference2 = (link_obj[l2], ["", ""])
    lim = j.get("limits", {})
    if lim.get("minOn"):
        jt.EnableAngleMin = True
        jt.AngleMin = math.degrees(lim["min"])
    if lim.get("maxOn"):
        jt.EnableAngleMax = True
        jt.AngleMax = math.degrees(lim["max"])
    made.append("%s:%s<->%s" % (j["name"], l1, l2))
print("stage5 joints:", len(made))
for m in made:
    print("  " + m)

# ---------------- stage 6: solve + drift check + save ----------------
doc.recompute()
before = {}
for lp in link_obj.values():
    for c in lp.Group:
        before[c.Name] = PLC(c.Placement)

rc = None
try:
    rc = asm.solve(False)
except Exception as e:
    print("solve EXCEPTION:", str(e).encode("ascii", "replace").decode())
doc.recompute()

drift = 0.0
worst = ""
for lp in link_obj.values():
    for c in lp.Group:
        d = (c.Placement.Base - before[c.Name].Base).Length
        if d > drift:
            drift, worst = d, c.Label
print("stage6 solve rc=%s max_drift_mm=%.6f (%s)" %
      (rc, drift, worst.encode("ascii", "replace").decode()))

# 无头保存的文档默认全不可见;显式置 True(ViewProvider 仍需 GUI 里跑一次
# tools/fc_gui_fixup.py,否则 Assembly 会报 redrawJointPlacements)
for o in doc.Objects:
    if o.TypeId in ("Part::Feature", "App::Part", "Assembly::AssemblyObject"):
        o.Visibility = True

doc.saveAs(OUT)
print("saved:", OUT, "objects:", len(doc.Objects))
