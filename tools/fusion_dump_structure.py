#!/usr/bin/env python3
"""从 Fusion 当前文档 dump 装配结构到 simulation/fusion_export/structure.json。

只读操作。上下文纪律:完整 JSON 落盘,stdout 只打摘要。
"""
import json
import math
import os
import sys
import urllib.request

MCP_URL = os.environ.get("FUSION_MCP_URL", "http://DESKTOP-59B42HE.local:19100/")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "simulation", "fusion_export")

WIN_OUT = "C:/Users/admin/sesame_export/structure.json"

DUMP_SCRIPT = r"""
import adsk.core, adsk.fusion, json, os

def run(context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    out = {"doc": app.activeDocument.name, "units": "cm",
           "joints": [], "rigidGroups": [], "grounded": [], "occs": {}}

    def vec(v):
        return [v.x, v.y, v.z]

    def occpath(o):
        try:
            return o.fullPathName if o else None
        except:
            return None

    colls = [(getattr(root, "allJoints", root.joints), "joint"),
             (getattr(root, "allAsBuiltJoints", root.asBuiltJoints), "asBuilt")]
    for coll, kind in colls:
        for j in coll:
            d = {"name": j.name, "kind": kind, "suppressed": j.isSuppressed,
                 "occ1": occpath(j.occurrenceOne), "occ2": occpath(j.occurrenceTwo)}
            jm = j.jointMotion
            rev = adsk.fusion.RevoluteJointMotion.cast(jm)
            if rev:
                d["type"] = "revolute"
                try:
                    d["axisWorld"] = vec(rev.rotationAxisVector)
                except Exception as e:
                    d["axisErr"] = str(e)
                lim = rev.rotationLimits
                d["limits"] = {"minOn": lim.isMinimumValueEnabled, "min": lim.minimumValue,
                               "maxOn": lim.isMaximumValueEnabled, "max": lim.maximumValue}
                d["value"] = rev.rotationValue
            else:
                d["type"] = jm.objectType.split("::")[-1]
            geo = None
            for attr in ("geometry", "geometryOrOriginOne"):
                g = getattr(j, attr, None)
                if g is not None:
                    geo = g
                    d["geoAttr"] = attr
                    break
            if geo is not None:
                try:
                    gg = adsk.fusion.JointGeometry.cast(geo)
                    if gg is None:
                        jo = adsk.fusion.JointOrigin.cast(geo)
                        gg = jo.geometry if jo else None
                    if gg is not None:
                        d["originWorld"] = vec(gg.origin)
                except Exception as e:
                    d["geoErr"] = str(e)
            out["joints"].append(d)

    for rg in getattr(root, "allRigidGroups", root.rigidGroups):
        try:
            occs = [occpath(rg.occurrences.item(i)) for i in range(rg.occurrences.count)]
        except Exception as e:
            occs = ["ERR:" + str(e)]
        out["rigidGroups"].append({"name": rg.name, "occs": occs})

    for occ in root.allOccurrences:
        o = {"component": occ.component.name,
             "transform": list(occ.transform2.asArray()),
             "bodies": occ.bRepBodies.count}
        try:
            o["grounded"] = occ.isGrounded
        except:
            pass
        try:
            o["groundToParent"] = occ.isGroundToParent
        except:
            pass
        out["occs"][occ.fullPathName] = o
        if o.get("grounded") or o.get("groundToParent"):
            out["grounded"].append(occ.fullPathName)

    path = "__WIN_OUT__"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f)
    print(json.dumps({"written": path, "occs": len(out["occs"]),
                      "joints": len(out["joints"])}))
"""


def call_fusion(script, timeout=180):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "execute_api_script", "arguments": {"script": script}}}
    req = urllib.request.Request(MCP_URL, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    raw = "\n".join(c.get("text", "") for c in resp["result"]["content"])
    a, b = raw.find("{"), raw.rfind("}")
    return json.loads(raw[a:b + 1])


def main():
    import subprocess
    ack = call_fusion(DUMP_SCRIPT.replace("__WIN_OUT__", WIN_OUT))
    print(f"fusion 已写盘: {ack}")
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "structure.json")
    subprocess.run(["sshpass", "-p", "lxy123", "scp",
                    "-o", "StrictHostKeyChecking=accept-new",
                    "admin@DESKTOP-59B42HE.local:sesame_export/structure.json",
                    path], check=True)
    with open(path) as f:
        data = json.load(f)

    # ---- 摘要 ----
    print(f"doc={data['doc']}  occs={len(data['occs'])}  已存 {os.path.relpath(path)}")
    by_type = {}
    for j in data["joints"]:
        by_type.setdefault(j["type"], []).append(j)
    for t, js in sorted(by_type.items()):
        print(f"joints[{t}] x{len(js)}")
    for j in by_type.get("revolute", []):
        ax = j.get("axisWorld", j.get("axisErr", "?"))
        og = j.get("originWorld", j.get("geoErr", "?"))
        lim = j.get("limits", {})
        deg = lambda v: round(math.degrees(v), 1) if isinstance(v, float) else v
        print(f"  {j['name']}: axis={ax} origin_cm={og} "
              f"lim=[{deg(lim.get('min'))},{deg(lim.get('max'))}] "
              f"occ1={j['occ1']} occ2={j['occ2']}")
    for rg in data["rigidGroups"]:
        print(f"rigidGroup {rg['name']}: {len(rg['occs'])} occs")
    print(f"grounded x{len(data['grounded'])}: {data['grounded']}")
    tops = sorted({p.split("+")[0] for p in data["occs"]})
    print(f"top-level occs x{len(tops)}:")
    for t in tops:
        print(f"  {t}")


if __name__ == "__main__":
    main()
