#!/usr/bin/env python3
"""GUI 运动测试:通过 FreeCADMCP 插件 RPC(9875)在打开的 FreeCAD 里逐关节摆动。

每个关节:绕世界系关节轴分帧转动子链(±AMP 度),求解器带动下游链,回零。
最后对账 9 个链的位姿。用户在 FreeCAD 窗口里直接看动画,零截图。
"""
import json
import sys
import time
import xmlrpc.client

FCSTD = "/home/lxy/Desktop/work/sesame-robot-micro/hardware/CAD/Sesame-Micro.FCStd"
STRUCT = "/home/lxy/Desktop/work/sesame-robot-micro/simulation/fusion_export/structure.json"
AMP = 20.0

srv = xmlrpc.client.ServerProxy("http://127.0.0.1:9875", allow_none=True)


def rpc(code):
    r = srv.execute_code(code)
    out = r.get("message", "")
    a, b = out.find("{"), out.rfind("}")
    if not r.get("success") or a == -1:
        raise RuntimeError("rpc failed: " + out[:400])
    return json.loads(out[a:b + 1])


INIT = """
import FreeCAD, FreeCADGui, json
path = %r
doc = None
for d in FreeCAD.listDocuments().values():
    if d.FileName == path:
        doc = d
if doc is None:
    doc = FreeCAD.openDocument(path)
FreeCAD.setActiveDocument(doc.Name)
try:
    v = FreeCADGui.getDocument(doc.Name).ActiveView
    v.viewIsometric()
    FreeCADGui.SendMsgToActiveView("ViewFit")
except Exception:
    pass
asm = next(o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject")
poses = {o.Label: [round(v, 9) for v in
                   (list(o.Placement.Base) + list(o.Placement.Rotation.Q))]
         for o in asm.Group if o.TypeId == "App::Part"}
print(json.dumps({"doc": doc.Name, "poses": poses}))
""" % FCSTD

WIGGLE = """
import FreeCAD, FreeCADGui, json, math, time
doc = FreeCAD.getDocument(%(doc)r)
asm = next(o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject")
# 整条子链一起指令(髋=upper+lower 刚性同转,膝=仅 lower),
# 求解器面对自洽构型无事可做,不给它自由发挥的余地
chain = [next(o for o in asm.Group if o.Label == lbl) for lbl in %(links)r]
o = FreeCAD.Vector(*%(origin)r)
ax = FreeCAD.Vector(*%(axis)r)
To = FreeCAD.Placement(o, FreeCAD.Rotation())
Tno = FreeCAD.Placement(-o, FreeCAD.Rotation())
P0 = [FreeCAD.Placement(l.Placement) for l in chain]
AMP = %(amp)r
STEPS = 6
seq = [AMP * i / STEPS for i in range(1, STEPS + 1)]
seq += [AMP - 2 * AMP * i / (2 * STEPS) for i in range(1, 2 * STEPS + 1)]
seq += [-AMP + AMP * i / STEPS for i in range(1, STEPS + 1)]
for th in seq:
    R = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(ax, th))
    M = To * R * Tno
    for l, p in zip(chain, P0):
        l.Placement = M * p
    doc.recompute()
    FreeCADGui.updateGui()
    time.sleep(0.02)
for l, p in zip(chain, P0):
    l.Placement = p
doc.recompute()
FreeCADGui.updateGui()
d = max((l.Placement.Base - p.Base).Length for l, p in zip(chain, P0))
print(json.dumps({"joint": %(name)r, "restored": d < 1e-9}))
"""

FINAL = """
import FreeCAD, json
doc = FreeCAD.getDocument(%(doc)r)
asm = next(o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject")
poses = {o.Label: [round(v, 9) for v in
                   (list(o.Placement.Base) + list(o.Placement.Rotation.Q))]
         for o in asm.Group if o.TypeId == "App::Part"}
print(json.dumps({"poses": poses}))
"""


def main():
    structure = json.load(open(STRUCT))

    for attempt in range(15):
        try:
            init = rpc(INIT)
            break
        except Exception as e:
            if attempt == 14:
                sys.exit("初始化失败: %s" % e)
            time.sleep(2)
    doc = init["doc"]
    print("文档 %s,%d 个链,视角已调好" % (doc, len(init["poses"])))

    for j in structure["joints"]:
        if j["type"] != "revolute":
            continue
        # hip_XX_rev 驱动 upper+lower(刚性同转,锁膝角);knee_XX_rev 仅 lower
        kind, leg = j["name"].split("_")[0], j["name"].split("_")[1]
        chain = ["upper_" + leg, "lower_" + leg] if kind == "hip" else ["lower_" + leg]
        code = WIGGLE % {
            "doc": doc, "links": chain, "name": j["name"], "amp": AMP,
            "origin": tuple(v * 10 for v in j["originWorld"]),
            "axis": tuple(j["axisWorld"]),
        }
        r = rpc(code)
        print("  %s -> %s ±%.0f°  %s" % (j["name"], "+".join(chain), AMP,
              "回零" if r["restored"] else "!!未还原"))

    fin = rpc(FINAL % {"doc": doc})
    bad = []
    for lbl, p0 in init["poses"].items():
        p1 = fin["poses"].get(lbl)
        d = max(abs(a - b) for a, b in zip(p0, p1)) if p1 else 999
        if d > 1e-6:
            bad.append((lbl, d))
    if bad:
        print("!! 位姿漂移:", bad)
        sys.exit(1)
    print("全部 %d 个链位姿无漂移,GUI 运动测试通过" % len(init["poses"]))


if __name__ == "__main__":
    main()
