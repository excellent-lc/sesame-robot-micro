#!/usr/bin/env python3
"""从 Fusion 导出物理属性(质量/质心/惯量/材料/外观)+ 用户参数。

写 Windows 盘再 scp 回 simulation/fusion_export/physical.json。
质心等坐标为装配世界系,单位 Fusion 原生(kg / cm / cm^2·kg)。
"""
import json
import os
import subprocess
import urllib.request

MCP_URL = os.environ.get("FUSION_MCP_URL", "http://DESKTOP-59B42HE.local:19100/")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "simulation", "fusion_export")

SCRIPT = r"""
import adsk.core, adsk.fusion, json, os

def run(context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    out = {"units": "kg/cm", "bodies": [], "params": []}

    def body_rec(b, owner):
        try:
            pp = b.physicalProperties
            com = pp.centerOfMass
            ok, xx, yy, zz, xy, yz, xz = pp.getXYZMomentsOfInertia()
            rec = {"owner": owner, "body": b.name,
                   "mass_kg": pp.mass, "vol_cm3": pp.volume,
                   "com_world_cm": [com.x, com.y, com.z],
                   "inertia_world": [xx, yy, zz, xy, yz, xz],
                   "visible": b.isLightBulbOn}
        except Exception as e:
            rec = {"owner": owner, "body": b.name, "err": str(e)}
        try:
            rec["material"] = b.material.name if b.material else None
        except Exception:
            rec["material"] = None
        try:
            rec["appearance"] = b.appearance.name if b.appearance else None
        except Exception:
            rec["appearance"] = None
        out["bodies"].append(rec)

    for b in root.bRepBodies:
        body_rec(b, "root")
    for occ in root.allOccurrences:
        for b in occ.bRepBodies:
            body_rec(b, occ.fullPathName)

    for p in des.userParameters:
        out["params"].append({"name": p.name, "expr": p.expression,
                              "value": p.value, "unit": p.unit,
                              "comment": p.comment})

    path = "C:/Users/admin/sesame_export/physical.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f)
    print(json.dumps({"bodies": len(out["bodies"]), "params": len(out["params"])}))
"""


def main():
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "execute_api_script", "arguments": {"script": SCRIPT}}}
    req = urllib.request.Request(MCP_URL, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.load(r)
        raw = "".join(c.get("text", "") for c in resp["result"]["content"])
        print("fusion:", raw[raw.find("{"):raw.rfind("}") + 1])
    except Exception as e:
        print("response lost (可能已执行):", e)

    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, "physical.json")
    subprocess.run(["sshpass", "-p", "lxy123", "scp",
                    "-o", "StrictHostKeyChecking=accept-new",
                    "admin@DESKTOP-59B42HE.local:sesame_export/physical.json", dst],
                   check=True)
    d = json.load(open(dst))
    total = sum(b.get("mass_kg", 0) for b in d["bodies"])
    mats = {}
    for b in d["bodies"]:
        mats[b.get("material")] = mats.get(b.get("material"), 0) + 1
    print("bodies=%d 总质量=%.1f g 材料分布=%s 参数=%d 个" %
          (len(d["bodies"]), total * 1000, mats, len(d["params"])))


if __name__ == "__main__":
    main()
