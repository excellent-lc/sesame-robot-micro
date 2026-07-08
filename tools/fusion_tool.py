#!/usr/bin/env python3
"""Fusion 常用操作工具箱(经 fusion_rpc 调局域网 Fusion MCP)。零脚本编写做机械调整。

子命令:
  selections                       读当前点选(面/圆柱/圆边:法线/孔位/包围盒),点选易被清空,一次抓全
  find --name 关键词               按名字模糊找 occurrence(路径/接地/位姿)
  faces --sel SEL [--normal x,y,z] [--area cm2]     按法线+面积过滤平面,列孔位
  mate  --a SEL --an x,y,z --aa cm2 --b SEL --bn x,y,z --ba cm2 [--solve]
                                   验证两面贴合(间隙mm/孔同心mm);--solve 解出所需平移
  move  --occ 完整路径 --t x,y,z [--unit mm|cm] [--rot ax,ay,az,deg --center x,y,z] [--force]
                                   世界系旋转+平移 occurrence;自动查关节/刚性组约束,打印前后位姿备份
  interf --sel SEL [--sel SEL...]  多组体间干涉检查(体积mm3+包围盒)

SEL 选择器: "occ:<fullPathName>"(含其子件) 或 "body:<根组件体名>"
单位: 几何回显=cm(API 原生);间隙/偏差字段带 _mm;move 输入默认 mm

典型流程(对面对孔):
  1. 用户在 Fusion 里 Ctrl 多选两个面 -> selections 抓几何
  2. mate --solve 解平移 -> move 应用 -> mate 复验 + interf 查干涉
"""
import argparse
import json
import sys

from fusion_rpc import call_fusion

# ---------- Fusion 侧公共 helper(本地拼接,不进对话) ----------
HELPERS = r'''import adsk.core, adsk.fusion, json, math

P = json.loads(r"""__PARAMS__""")

def _v3(p):
    return [round(p.x, 4), round(p.y, 4), round(p.z, 4)]

def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def _circles(f):
    seen, res = set(), []
    for lp in f.loops:
        for ed in lp.edges:
            eg = ed.geometry
            if eg.objectType.split("::")[-1] == "Circle3D":
                k = (round(eg.center.x, 3), round(eg.center.y, 3),
                     round(eg.center.z, 3), round(eg.radius, 3))
                if k not in seen:
                    seen.add(k)
                    res.append({"c": _v3(eg.center), "r": round(eg.radius, 4)})
    return res

def _face_normal(f):
    ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
    return n if ok else f.geometry.normal

def _iter_bodies(root, sel):
    kind, _, val = sel.partition(":")
    if kind == "occ":
        for o in root.allOccurrences:
            fp = o.fullPathName
            if fp == val or fp.startswith(val + "+"):
                for b in o.bRepBodies:
                    yield b
    else:
        for b in root.bRepBodies:
            if b.name == val:
                yield b

def _find_planar_faces(root, sel, normal=None, area=None):
    res = []
    for b in _iter_bodies(root, sel):
        for f in b.faces:
            if f.geometry.objectType.split("::")[-1] != "Plane":
                continue
            n = _face_normal(f)
            if normal and _dot((n.x, n.y, n.z), normal) <= 0.999:
                continue
            if area is not None and abs(f.area - area) > max(0.05, area * 0.02):
                continue
            res.append(f)
    return res

def _face_brief(f):
    return {"origin": _v3(f.geometry.origin), "normal": _v3(_face_normal(f)),
            "area": round(f.area, 3), "circles": _circles(f), "body": f.body.name,
            "occ": f.assemblyContext.fullPathName if f.assemblyContext else None}

'''

PROLOGUE = '''    app = adsk.core.Application.get()
    ui = app.userInterface
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    out = {}
'''

# ---------- 各子命令的 Fusion 侧脚本体(在 run(context) 内执行) ----------
BODIES = {}

BODIES["selections"] = r'''
sels = ui.activeSelections
out["n"] = sels.count
out["sels"] = []
for i in range(sels.count):
    e = sels.item(i).entity
    info = {"objType": e.objectType.split("::")[-1]}
    occ = getattr(e, "assemblyContext", None)
    info["occ"] = occ.fullPathName if occ else None
    try:
        info["body"] = e.body.name
    except Exception:
        pass
    g = getattr(e, "geometry", None)
    if g is not None:
        t = g.objectType.split("::")[-1]
        info["geom"] = t
        if t == "Plane":
            f = adsk.fusion.BRepFace.cast(e)
            n = _face_normal(f) if f else g.normal
            info["origin"] = _v3(g.origin)
            info["normal"] = _v3(n)
            if f:
                info["area"] = round(f.area, 3)
                info["circles"] = _circles(f)
        elif t == "Cylinder":
            info["origin"] = _v3(g.origin)
            info["axis"] = _v3(g.axis)
            info["r"] = round(g.radius, 4)
        elif t == "Circle3D":
            info["center"] = _v3(g.center)
            info["r"] = round(g.radius, 4)
    bb = getattr(e, "boundingBox", None)
    if bb:
        info["bb"] = [_v3(bb.minPoint), _v3(bb.maxPoint)]
    out["sels"].append(info)
print(json.dumps(out))
'''

BODIES["find"] = r'''
key = P["name"].lower()
hits = []
for o in root.allOccurrences:
    if key in o.component.name.lower() or key in o.fullPathName.lower():
        hits.append({"path": o.fullPathName, "comp": o.component.name,
                     "grounded": bool(getattr(o, "isGrounded", False)),
                     "bodies": o.bRepBodies.count,
                     "t": [round(x, 5) for x in o.transform2.asArray()]})
out["n"] = len(hits)
out["hits"] = hits[:P["limit"]]
if len(hits) > P["limit"]:
    out["truncated"] = True
print(json.dumps(out))
'''

BODIES["faces"] = r'''
faces = _find_planar_faces(root, P["sel"], P.get("normal"), P.get("area"))
out["n"] = len(faces)
out["faces"] = [_face_brief(f) for f in faces[:P["limit"]]]
if len(faces) > P["limit"]:
    out["truncated"] = True
print(json.dumps(out))
'''

BODIES["mate"] = r'''
fa = _find_planar_faces(root, P["a_sel"], P.get("a_normal"), P.get("a_area"))
fb = _find_planar_faces(root, P["b_sel"], P.get("b_normal"), P.get("b_area"))
if len(fa) != 1 or len(fb) != 1:
    out["err"] = "need exactly 1 face each, got A=%d B=%d; refine --normal/--area" % (len(fa), len(fb))
    out["A"] = [_face_brief(f) for f in fa[:5]]
    out["B"] = [_face_brief(f) for f in fb[:5]]
    print(json.dumps(out))
    return
A, B = fa[0], fb[0]
na, nb = _face_normal(A), _face_normal(B)
na = (na.x, na.y, na.z)
nb = (nb.x, nb.y, nb.z)
out["normals_dot"] = round(_dot(na, nb), 6)
ao, bo = A.geometry.origin, B.geometry.origin
gap = _dot(nb, (ao.x - bo.x, ao.y - bo.y, ao.z - bo.z))
out["plane_gap_mm"] = round(gap * 10, 5)
ca, cb = _circles(A), _circles(B)
out["holes_a"], out["holes_b"] = len(ca), len(cb)
pairs, deltas = [], []
for c in (ca if cb else []):
    best = min(cb, key=lambda t: sum((c["c"][i] - t["c"][i]) ** 2 for i in range(3)))
    d = [best["c"][i] - c["c"][i] for i in range(3)]
    deltas.append(d)
    dn = _dot(nb, d)
    inp = [d[i] - dn * nb[i] for i in range(3)]
    pairs.append({"r_a": c["r"], "r_b": best["r"],
                  "offset_inplane_mm": round(math.sqrt(_dot(inp, inp)) * 10, 4)})
out["pairs"] = pairs
if P.get("solve"):
    if out["normals_dot"] > -0.999:
        out["solve"] = {"err": "normals not anti-parallel, rotation needed first"}
    elif deltas:
        mean = [sum(d[i] for d in deltas) / len(deltas) for i in range(3)]
        spread = max(math.sqrt(sum((d[i] - mean[i]) ** 2 for i in range(3))) for d in deltas)
        out["solve"] = {"t_cm": [round(x, 5) for x in mean],
                        "t_mm": [round(x * 10, 4) for x in mean],
                        "spread_mm": round(spread * 10, 4),
                        "pure_translation_ok": spread < 0.01}
    else:
        t = [-gap * nb[i] for i in range(3)]
        out["solve"] = {"t_cm": [round(x, 5) for x in t],
                        "t_mm": [round(x * 10, 4) for x in t],
                        "note": "no hole pairs, plane-gap-only translation"}
print(json.dumps(out))
'''

BODIES["move"] = r'''
target = None
for o in root.allOccurrences:
    if o.fullPathName == P["occ"]:
        target = o
        break
if target is None:
    print(json.dumps({"err": "occ not found: " + P["occ"]}))
    return
hits = []
for coll in (getattr(root, "allJoints", root.joints),
             getattr(root, "allAsBuiltJoints", root.asBuiltJoints)):
    for j in coll:
        for jo in (j.occurrenceOne, j.occurrenceTwo):
            try:
                if jo and (jo.fullPathName == P["occ"] or jo.fullPathName.startswith(P["occ"] + "+")):
                    hits.append("joint:" + j.name)
            except Exception:
                pass
for rg in getattr(root, "allRigidGroups", root.rigidGroups):
    try:
        for i in range(rg.occurrences.count):
            fp = rg.occurrences.item(i).fullPathName
            if fp == P["occ"] or fp.startswith(P["occ"] + "+"):
                hits.append("rg:" + rg.name)
    except Exception:
        pass
out["constraints"] = hits
if hits and not P.get("force"):
    out["abort"] = "constrained; rerun with --force to move anyway"
    print(json.dumps(out))
    return
m = target.transform2.copy()
out["before"] = [round(x, 5) for x in m.asArray()]
if P.get("rot"):
    r = P["rot"]
    rm = adsk.core.Matrix3D.create()
    rm.setToRotation(r["deg"] * math.pi / 180.0,
                     adsk.core.Vector3D.create(r["axis"][0], r["axis"][1], r["axis"][2]),
                     adsk.core.Point3D.create(r["center"][0], r["center"][1], r["center"][2]))
    m.transformBy(rm)
a = list(m.asArray())
t = P.get("t") or [0.0, 0.0, 0.0]
a[3] += t[0]
a[7] += t[1]
a[11] += t[2]
m2 = adsk.core.Matrix3D.create()
m2.setWithArray(a)
target.transform2 = m2
out["after"] = [round(x, 5) for x in target.transform2.asArray()]
try:
    if des.designType == adsk.fusion.DesignTypes.ParametricDesignType and des.snapshots.hasPendingSnapshot:
        des.snapshots.add()
        out["snapshot"] = True
except Exception as e:
    out["snapErr"] = str(e)
print(json.dumps(out))
'''

BODIES["interf"] = r'''
ents = adsk.core.ObjectCollection.create()
nb = 0
for s in P["sels"]:
    for b in _iter_bodies(root, s):
        ents.add(b)
        nb += 1
out["bodies"] = nb
inp = des.createInterferenceInput(ents)
res = des.analyzeInterference(inp)
out["pairs"] = []
for i in range(res.count):
    r = res.item(i)
    rec = {}
    try:
        ib = r.interferenceBody
        rec["vol_mm3"] = round(ib.volume * 1000, 5)
        bb = ib.boundingBox
        rec["bb"] = [_v3(bb.minPoint), _v3(bb.maxPoint)]
    except Exception as e:
        rec["err"] = str(e)
    out["pairs"].append(rec)
print(json.dumps(out))
'''


def build_script(cmd, params):
    body = BODIES[cmd].strip("\n")
    indented = "\n".join(("    " + ln if ln.strip() else ln) for ln in body.splitlines())
    return (HELPERS.replace("__PARAMS__", json.dumps(params))
            + "\ndef run(context):\n" + PROLOGUE + indented + "\n")


def fvec(s, n=3):
    v = [float(x) for x in s.split(",")]
    if len(v) != n:
        raise argparse.ArgumentTypeError("expect %d comma-separated numbers" % n)
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout", type=int, default=120)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selections")

    p = sub.add_parser("find")
    p.add_argument("--name", required=True)
    p.add_argument("--limit", type=int, default=30)

    p = sub.add_parser("faces")
    p.add_argument("--sel", required=True, help="occ:<path> 或 body:<name>")
    p.add_argument("--normal", type=fvec)
    p.add_argument("--area", type=float, help="cm2")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("mate")
    p.add_argument("--a", required=True, dest="a_sel")
    p.add_argument("--an", type=fvec, dest="a_normal")
    p.add_argument("--aa", type=float, dest="a_area")
    p.add_argument("--b", required=True, dest="b_sel")
    p.add_argument("--bn", type=fvec, dest="b_normal")
    p.add_argument("--ba", type=float, dest="b_area")
    p.add_argument("--solve", action="store_true")

    p = sub.add_parser("move")
    p.add_argument("--occ", required=True, help="occurrence fullPathName")
    p.add_argument("--t", type=fvec, help="平移 x,y,z")
    p.add_argument("--rot", help="ax,ay,az,deg 世界系轴角")
    p.add_argument("--center", type=fvec, help="旋转中心(默认原点)")
    p.add_argument("--unit", choices=["mm", "cm"], default="mm")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("interf")
    p.add_argument("--sel", action="append", required=True, dest="sels")

    args = ap.parse_args()
    params = {k: v for k, v in vars(args).items()
              if k not in ("cmd", "timeout") and v is not None}

    if args.cmd == "move":
        scale = 0.1 if args.unit == "mm" else 1.0
        if args.t:
            params["t"] = [x * scale for x in args.t]
        if args.rot:
            r = [float(x) for x in args.rot.split(",")]
            if len(r) != 4:
                sys.exit("--rot 需要 ax,ay,az,deg 四个数")
            c = [x * scale for x in (args.center or [0, 0, 0])]
            params["rot"] = {"axis": r[:3], "deg": r[3], "center": c}
        params.pop("unit", None)
        params.pop("center", None)
        if not params.get("t") and not params.get("rot"):
            sys.exit("move 需要 --t 和/或 --rot")

    out = call_fusion(build_script(args.cmd, params), args.timeout)
    print(out, end="" if out.endswith("\n") else "\n")


if __name__ == "__main__":
    main()
