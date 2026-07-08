"""探查 STEP 导入 FreeCAD 后的层级/命名(ASCII 输出)。用 freecadcmd 跑。"""
import FreeCAD
import Import

P = "/home/lxy/Desktop/work/sesame-robot-micro/hardware/CAD/Sesame-Micro.step"


def a(s):
    return s.encode("ascii", "replace").decode()


doc = FreeCAD.newDocument("probe")
Import.insert(P, "probe")

types = {}
for o in doc.Objects:
    types[o.TypeId] = types.get(o.TypeId, 0) + 1
print("total objects:", len(doc.Objects))
for t, n in sorted(types.items()):
    print(f"  {t}: {n}")

roots = [o for o in doc.Objects if not o.InList]
print("roots:", len(roots))


def walk(o, depth, lines, maxd):
    kids = list(getattr(o, "Group", []) or [])
    solids = ""
    if hasattr(o, "Shape"):
        solids = f" solids={len(o.Shape.Solids)}"
    lines.append("  " * depth + f"{o.TypeId.split('::')[-1]} '{a(o.Label)}' kids={len(kids)}{solids}")
    if depth < maxd:
        for k in kids[:10]:
            walk(k, depth + 1, lines, maxd)
        if len(kids) > 10:
            lines.append("  " * (depth + 1) + f"...({len(kids) - 10} more)")


for r in roots[:2]:
    lines = []
    walk(r, 0, lines, 2)
    print("\n".join(lines[:80]))
