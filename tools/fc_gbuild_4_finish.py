"""GUI 重建 phase4:机身散装件按体积恢复真名 + 视角 + 存盘。经 fc_rpc 执行。

Fusion 根级 body 的名字不进 STEP(变 COMPOUNDxxx),
用 physical.json 里 root body 的体积对号改回。幂等,可重复跑。
"""
import FreeCAD
import FreeCADGui
import json

REPO = "/home/lxy/Desktop/work/sesame-robot-micro"
phys = json.load(open(REPO + "/simulation/fusion_export/physical.json"))
root_bodies = [b for b in phys["bodies"] if b["owner"] == "root"]

doc = FreeCAD.getDocument("SesameMicro")
renamed = {}
for f in doc.Objects:
    if f.TypeId != "Part::Feature" or not f.Label.startswith("COMPOUND"):
        continue
    v = f.Shape.Volume / 1000.0
    match = [b for b in root_bodies if abs(b["vol_cm3"] - v) < 0.01]
    if len(match) == 1:
        renamed[f.Label] = match[0]["body"]
        f.Label = match[0]["body"]
for o in doc.Objects:
    if o.TypeId == "App::Part" and o.Label.startswith("COMPOUND") \
            and {c.Label for c in o.Group} & {b["body"] for b in root_bodies}:
        o.Label = "frame_parts"
doc.recompute()
doc.save()
gd = FreeCADGui.getDocument(doc.Name)
if gd.ActiveView:
    gd.ActiveView.viewIsometric()
    gd.ActiveView.fitAll()
print(json.dumps({"renamed": renamed, "saved": True}, ensure_ascii=False))
