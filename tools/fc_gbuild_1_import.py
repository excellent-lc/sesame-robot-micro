"""GUI 重建 phase1:关闭旧文档,ImportGui 导入完整 STEP(带颜色)。经 fc_rpc 执行。"""
import FreeCAD
import ImportGui
import json

for n in list(FreeCAD.listDocuments()):
    FreeCAD.closeDocument(n)
doc = FreeCAD.newDocument("SesameMicro")
ImportGui.insert(
    "/home/lxy/Desktop/work/sesame-robot-micro/simulation/fusion_export/modbot_full.step",
    "SesameMicro")
roots = [o for o in doc.Objects if not o.InList and o.TypeId == "App::Part"]
tops = list(roots[0].Group) if roots else []
colored = 0
for o in doc.Objects:
    if o.TypeId == "Part::Feature":
        dc = o.ViewObject.DiffuseColor
        if dc and any(c[:3] != (0.8, 0.8, 0.8) for c in dc):
            colored += 1
print(json.dumps({"objs": len(doc.Objects), "tops": len(tops),
                  "colored_features": colored}))
