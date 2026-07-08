"""探查2:全部顶层对象+位姿;Assembly 工作台无头可用性。ASCII 输出。"""
import FreeCAD
import Import

P = "/home/lxy/Desktop/work/sesame-robot-micro/hardware/CAD/Sesame-Micro.step"


def a(s):
    return s.encode("ascii", "replace").decode()


doc = FreeCAD.newDocument("probe")
Import.insert(P, "probe")
root = [o for o in doc.Objects if not o.InList][0]
print("== top-level children of", a(root.Label), "==")
for k in root.Group:
    pl = k.Placement
    p = pl.Base
    ax, ang = pl.Rotation.Axis, pl.Rotation.Angle
    solids = len(k.Shape.Solids) if hasattr(k, "Shape") else sum(
        len(c.Shape.Solids) for c in k.OutListRecursive if hasattr(c, "Shape"))
    print(f"{k.TypeId.split('::')[-1]:8s} '{a(k.Label)}' pos_mm=({p.x:.2f},{p.y:.2f},{p.z:.2f}) "
          f"rot=({ax.x:.2f},{ax.y:.2f},{ax.z:.2f})@{ang*57.2958:.1f}deg")

print("== assembly workbench headless test ==")
d2 = FreeCAD.newDocument("asmtest")
try:
    asm = d2.addObject("Assembly::AssemblyObject", "Assembly")
    print("AssemblyObject: OK", asm.TypeId)
except Exception as e:
    print("AssemblyObject: FAIL", a(str(e)))
try:
    import JointObject
    print("import JointObject: OK")
    try:
        jg = d2.addObject("Assembly::JointGroup", "Joints")
        print("JointGroup: OK")
    except Exception as e:
        print("JointGroup: FAIL", a(str(e)))
except Exception as e:
    print("import JointObject: FAIL", a(str(e)))
try:
    import UtilsAssembly
    print("import UtilsAssembly: OK")
except Exception as e:
    print("import UtilsAssembly: FAIL", a(str(e)))
