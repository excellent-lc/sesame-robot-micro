"""GUI 重建 phase3:关节 + ViewProvider + 接地 + 限位 + 求解校验 + 存盘。经 fc_rpc 执行。"""
import FreeCAD
import FreeCADGui
import JointObject
import json
import math

REPO = "/home/lxy/Desktop/work/sesame-robot-micro"
OUT = REPO + "/hardware/CAD/Sesame-Micro.FCStd"
structure = json.load(open(REPO + "/simulation/fusion_export/structure.json"))
links = json.load(open(REPO + "/simulation/fusion_export/links.json"))

FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly").SetBool(
    "SolveInJointCreation", False)

doc = FreeCAD.getDocument("SesameMicro")
V, ROT, PLC = FreeCAD.Vector, FreeCAD.Rotation, FreeCAD.Placement
asm = next(o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject")
jg = next(o for o in doc.Objects if o.TypeId == "Assembly::JointGroup")
link_obj = {o.Label: o for o in asm.Group if o.TypeId == "App::Part"}

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
JointObject.ViewProviderGroundedJoint(ground.ViewObject)

made = 0
for j in structure["joints"]:
    if j["type"] != "revolute":
        continue
    l1, l2 = node_link[node(j["occ1"])], node_link[node(j["occ2"])]
    o, ax = j["originWorld"], j["axisWorld"]
    world = PLC(V(o[0] * 10, o[1] * 10, o[2] * 10),
                ROT(V(0, 0, 1), V(ax[0], ax[1], ax[2])))
    jt = doc.addObject("App::FeaturePython", j["name"])
    jg.addObject(jt)
    JointObject.Joint(jt, 1)
    JointObject.ViewProviderJoint(jt.ViewObject)
    jt.Detach1 = True
    jt.Detach2 = True
    jt.Placement1 = world
    jt.Placement2 = world
    jt.Reference1 = (link_obj[l1], ["", ""])
    jt.Reference2 = (link_obj[l2], ["", ""])
    lim = j.get("limits", {})
    if lim.get("minOn"):
        jt.EnableAngleMin = True
        jt.AngleMin = math.degrees(lim["min"])
    if lim.get("maxOn"):
        jt.EnableAngleMax = True
        jt.AngleMax = math.degrees(lim["max"])
    jt.Visibility = False
    made += 1

for o in doc.Objects:
    if o.TypeId in ("Part::Feature", "App::Part", "Assembly::AssemblyObject"):
        if not o.Visibility:
            o.Visibility = True

doc.recompute()
before = {}
for lp in link_obj.values():
    for c in lp.Group:
        before[c.Name] = PLC(c.Placement)
rc = asm.solve(False)
doc.recompute()
drift = 0.0
for lp in link_obj.values():
    for c in lp.Group:
        drift = max(drift, (c.Placement.Base - before[c.Name].Base).Length)

vp_ok = sum(1 for o in doc.Objects if hasattr(o, "JointType")
            and hasattr(o.ViewObject.Proxy, "switch_JCS1"))

doc.saveAs(OUT)
gd = FreeCADGui.getDocument(doc.Name)
if gd.ActiveView:
    gd.ActiveView.viewIsometric()
    gd.ActiveView.fitAll()
print(json.dumps({"joints": made, "solve_rc": rc, "drift_mm": round(drift, 6),
                  "vp_with_scene_nodes": vp_ok, "saved": OUT}))
