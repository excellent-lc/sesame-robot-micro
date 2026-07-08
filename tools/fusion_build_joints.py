#!/usr/bin/env python3
"""按 structure.json 重建 Modbot 的 20 个 asBuilt 关节 + 4 处接地(装配树重组后)。

输入: simulation/fusion_export/structure.json(重组前 dump,关节权威定义)
      simulation/fusion_export/regroup_mapping.json(旧root路径 -> 新suffix)
路径映射: 新路径 = 组前缀 + "+" + suffix + 子路径余部(组前缀按 GROUPS 表)。

配方(2026-07-07 验证): revolute 在 occ1/occ2 体上找轴平行+过原点的圆柱面,
JointGeometry.createByNonPlanarFace + MiddleKeyPoint,
input.setAsRevoluteJointMotion(ZAxisJointDirection),加限位;rigid 无需几何。

坑: Python.Run 单行 >~3.5KB 静默不执行 -> params JSON 一律 indent=1;
    调用间隔 >=5s;每批 <=4 关节;创建后按名字幂等跳过。
"""
import json
import sys
import time

sys.path.insert(0, "/home/lxy/Desktop/work/sesame-robot-micro/tools")
from fusion_rpc import call_fusion

ROOT = "/home/lxy/Desktop/work/sesame-robot-micro"
SV = "DM-S0020 2.1G Ultra-Micro Servo"

# 旧 root 路径 -> 组前缀(与重组 PARTS 一致)
GROUPS = {
    SV + ":3": "body:1", SV + ":4": "body:1", SV + ":1": "body:1", SV + ":2": "body:1",
    "Waveshare 1315 0.49in i2c 64x32 oled display v1:1": "body:1+electronics:1",
    "SPDT Mini Slide Switch:1": "body:1+electronics:1",
    "proto-board:1": "body:1+electronics:1",
    "Seeed Studio XIAO-ESP32-S3:1": "body:1+electronics:1",
    "hip_lf:1": "leg_lf:1", SV + ":5": "leg_lf:1", "F-L3:1": "leg_lf:1",
    "hip_rf:1": "leg_rf:1", SV + ":7": "leg_rf:1", "F-R3:1": "leg_rf:1",
    "hip_lr:1": "leg_lr:1", SV + ":8": "leg_lr:1", "F-L4:1": "leg_lr:1",
    "hip_rr:1": "leg_rr:1", SV + ":6": "leg_rr:1", "F-R4:1": "leg_rr:1",
}

HDR = r'''import adsk.core, adsk.fusion, json, math

P = json.loads(r"""__P__""")

def run(context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
'''

BUILD = r'''
def by_path(p):
    for o in root.allOccurrences:
        if o.fullPathName == p:
            return o
    return None

def find_cyl(occ, origin, axis):
    op = adsk.core.Point3D.create(*origin)
    best = None
    for b in occ.bRepBodies:
        for f in b.faces:
            g = f.geometry
            if g.objectType.split("::")[-1] != "Cylinder":
                continue
            a = g.axis
            dt = abs(a.x * axis[0] + a.y * axis[1] + a.z * axis[2])
            if dt < 0.999:
                continue
            ao = g.origin
            v = adsk.core.Vector3D.create(op.x - ao.x, op.y - ao.y, op.z - ao.z)
            proj = v.x * a.x + v.y * a.y + v.z * a.z
            d2 = v.length ** 2 - proj ** 2
            d = math.sqrt(max(d2, 0.0))
            if best is None or d < best[0]:
                best = (d, f)
    return best

existing = set()
for j in root.allAsBuiltJoints:
    existing.add(j.name)
res = []
for jd in P["joints"]:
    if jd["name"] in existing:
        res.append({"name": jd["name"], "skip": "exists"})
        continue
    o1, o2 = by_path(jd["occ1"]), by_path(jd["occ2"])
    if o1 is None or o2 is None:
        res.append({"name": jd["name"], "err": "occ not found",
                    "o1": jd["occ1"], "found1": o1 is not None})
        continue
    if jd["type"] == "revolute":
        hit = find_cyl(o1, jd["originWorld"], jd["axisWorld"]) or \
              find_cyl(o2, jd["originWorld"], jd["axisWorld"])
        if hit is None or hit[0] > 0.05:
            res.append({"name": jd["name"], "err": "no cyl face",
                        "d": None if hit is None else round(hit[0], 4)})
            continue
        geo = adsk.fusion.JointGeometry.createByNonPlanarFace(
            hit[1], adsk.fusion.JointKeyPointTypes.MiddleKeyPoint)
        inp = root.asBuiltJoints.createInput(o1, o2, geo)
        inp.setAsRevoluteJointMotion(adsk.fusion.JointDirections.ZAxisJointDirection)
        j = root.asBuiltJoints.add(inp)
        j.name = jd["name"]
        jm = j.jointMotion
        lim = jd.get("limits") or {}
        if lim.get("minOn"):
            jm.rotationLimits.isMinimumValueEnabled = True
            jm.rotationLimits.minimumValue = lim["min"]
        if lim.get("maxOn"):
            jm.rotationLimits.isMaximumValueEnabled = True
            jm.rotationLimits.maximumValue = lim["max"]
        av = jm.rotationAxisVector
        dt = av.x * jd["axisWorld"][0] + av.y * jd["axisWorld"][1] + av.z * jd["axisWorld"][2]
        res.append({"name": jd["name"], "ok": 1, "d_mm": round(hit[0] * 10, 3),
                    "axis_dot": round(dt, 4)})
    else:
        inp = root.asBuiltJoints.createInput(o1, o2, None)
        j = root.asBuiltJoints.add(inp)
        j.name = jd["name"]
        res.append({"name": jd["name"], "ok": 1})
_s = json.dumps({"nonce": P.get("nonce"), "data": res})
try:
    open("C:/Users/admin/sesame_export/rpc_out.json", "w").write(_s)
except Exception:
    pass
print(_s)
'''

GROUND = r'''
res = []
for p in P["paths"]:
    hit = None
    for o in root.allOccurrences:
        if o.fullPathName == p:
            hit = o
            break
    if hit is None:
        res.append({"p": p, "err": "not found"})
        continue
    hit.isGrounded = True
    res.append({"p": p, "grounded": bool(hit.isGrounded)})
_s = json.dumps({"nonce": P.get("nonce"), "data": res})
print(_s)
'''

VERIFY = r'''
js = []
for j in root.allAsBuiltJoints:
    rec = {"name": j.name, "suppressed": j.isSuppressed}
    try:
        jm = j.jointMotion
        rec["jt"] = jm.jointType
        if jm.jointType == adsk.fusion.JointTypes.RevoluteJointType:
            rec["deg"] = round(jm.rotationValue * 180 / math.pi, 3)
            rec["lim"] = [round(jm.rotationLimits.minimumValue, 4),
                          round(jm.rotationLimits.maximumValue, 4)]
    except Exception as e:
        rec["err"] = str(e)[:60]
    js.append(rec)
grounded = [o.fullPathName for o in root.allOccurrences if getattr(o, "isGrounded", False)]
_s = json.dumps({"nonce": P.get("nonce"), "data": {"n": len(js), "joints": js,
                                                   "grounded": grounded}})
print(_s)
'''


def rpc(body, params, timeout=90, retries=3):
    import uuid
    params = dict(params)
    params["nonce"] = str(uuid.uuid4())[:8]
    script = HDR.replace("__P__", json.dumps(params, indent=1)) + "\n".join(
        "    " + ln for ln in body.strip("\n").splitlines()) + "\n"
    last = None
    for _ in range(retries):
        try:
            raw = call_fusion(script, timeout)
            obj = json.loads(raw)
            time.sleep(5)
            return obj["data"]
        except Exception as e:
            last = e
            time.sleep(10)
    sys.exit("rpc 失败: %s" % last)


def remap(p):
    for old, grp in GROUPS.items():
        if p == old or p.startswith(old + "+"):
            return grp + "+" + MAP[old] + p[len(old):]
    return p


def main():
    S = json.load(open(ROOT + "/simulation/fusion_export/structure.json"))
    global MAP
    MAP = json.load(open(ROOT + "/simulation/fusion_export/regroup_mapping.json"))

    joints = []
    for j in S["joints"]:
        joints.append({"name": j["name"], "type": j["type"],
                       "occ1": remap(j["occ1"]), "occ2": remap(j["occ2"]),
                       "originWorld": j.get("originWorld"),
                       "axisWorld": j.get("axisWorld"),
                       "limits": j.get("limits")})

    ok = skip = 0
    for i in range(0, len(joints), 4):
        batch = joints[i:i + 4]
        res = rpc(BUILD, {"joints": batch}, timeout=120)
        for r in res:
            if "err" in r:
                sys.exit("关节失败: %s" % json.dumps(r, ensure_ascii=False))
            ok += 1 if r.get("ok") else 0
            skip += 1 if r.get("skip") else 0
            if r.get("ok") and "axis_dot" in r:
                print("  %-14s d=%.3fmm axis_dot=%.4f" % (r["name"], r["d_mm"], r["axis_dot"]))
        print("批%d/%d: 建%d 跳%d" % (i // 4 + 1, (len(joints) + 3) // 4, ok, skip))

    gpaths = [remap(p) for p in S["grounded"]]
    res = rpc(GROUND, {"paths": gpaths})
    bad = [r for r in res if not r.get("grounded")]
    print("接地: %d/%d" % (len(res) - len(bad), len(res)), "失败:" if bad else "", bad or "")

    v = rpc(VERIFY, {})
    revs = [j for j in v["joints"] if "deg" in j]
    print("验证: 共%d关节, %d revolute, 全零位=%s, 接地%d处" % (
        v["n"], len(revs), all(abs(j["deg"]) < 1e-6 for j in revs), len(v["grounded"])))
    for j in revs:
        if j["lim"] != [-1.5708, 1.5708]:
            print("  !! 限位异常:", j)


if __name__ == "__main__":
    main()
