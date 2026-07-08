"""GUI 一次性修复:给无头构建的 Sesame-Micro.FCStd 补关节 ViewProvider + 可见性。

用法(FreeCAD GUI 开着、文档已打开时):
    python3 tools/fc_rpc.py tools/fc_gui_fixup.py

原理:无头保存的文档里 FeaturePython 关节没有视图代理(Proxy=0),对象全不可见。
热挂 Proxy 不会触发 attach()(缺 switch_JCS1 等场景节点),所以流程必须是:
挂 Proxy -> 存盘 -> 关闭重开(restore 时才会正常调用 attach)。
仅在用 fc_build_assembly.py 重新生成 FCStd 后需要跑一次。
"""
import FreeCAD
import FreeCADGui
import json
import JointObject

PATH = "/home/lxy/Desktop/work/sesame-robot-micro/hardware/CAD/Sesame-Micro.FCStd"

doc = FreeCAD.getDocument("Sesame_Micro")
fixed = {"vp_joint": 0, "vp_ground": 0, "shown": 0}
for o in doc.Objects:
    if hasattr(o, "JointType"):
        if not hasattr(o.ViewObject.Proxy, "redrawJointPlacements"):
            JointObject.ViewProviderJoint(o.ViewObject)
            fixed["vp_joint"] += 1
        o.Visibility = False
    elif hasattr(o, "ObjectToGround"):
        if not isinstance(o.ViewObject.Proxy, JointObject.ViewProviderGroundedJoint):
            JointObject.ViewProviderGroundedJoint(o.ViewObject)
            fixed["vp_ground"] += 1
    elif o.TypeId in ("Part::Feature", "App::Part", "Assembly::AssemblyObject"):
        if not o.Visibility:
            o.Visibility = True
            fixed["shown"] += 1
doc.recompute()
doc.save()

# 关键:关闭重开,让 ViewProvider 走标准 attach 流程(热挂不会建场景节点)
FreeCAD.closeDocument(doc.Name)
doc = FreeCAD.openDocument(PATH)
FreeCAD.setActiveDocument(doc.Name)
gd = FreeCADGui.getDocument(doc.Name)
if gd.ActiveView:
    gd.ActiveView.viewIsometric()
    gd.ActiveView.fitAll()

ok = sum(1 for o in doc.Objects if hasattr(o, "JointType")
         and hasattr(o.ViewObject.Proxy, "switch_JCS1"))
fixed["vp_attached_after_reopen"] = ok
print(json.dumps(fixed))
