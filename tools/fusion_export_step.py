#!/usr/bin/env python3
"""从 Fusion 导出全量 STEP(临时显示隐藏体,导出后恢复),scp 回本地。

产物: simulation/fusion_export/modbot_full.step
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
    toggled = []
    for b in root.bRepBodies:
        if not b.isLightBulbOn:
            b.isLightBulbOn = True
            toggled.append(("root", b.name))
    for occ in root.allOccurrences:
        for b in occ.bRepBodies:
            if not b.isLightBulbOn:
                b.isLightBulbOn = True
                toggled.append((occ.fullPathName, b.name))
    try:
        em = des.exportManager
        path = "C:/Users/admin/sesame_export/modbot_full.step"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        opts = em.createSTEPExportOptions(path, root)
        em.execute(opts)
    finally:
        # 无论导出成败都恢复隐藏状态
        for owner, bname in toggled:
            bodies = root.bRepBodies if owner == "root" else None
            if bodies is None:
                for occ in root.allOccurrences:
                    if occ.fullPathName == owner:
                        bodies = occ.bRepBodies
                        break
            if bodies:
                for b in bodies:
                    if b.name == bname:
                        b.isLightBulbOn = False
    print(json.dumps({"exported": True,
                      "unhidden_during_export": ["%s/%s" % t for t in toggled]}))
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
        print("fusion:", raw[raw.find("{"):raw.rfind("}") + 1][:300])
    except Exception as e:
        print("response lost (导出可能已完成):", e)

    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, "modbot_full.step")
    subprocess.run(["sshpass", "-p", "lxy123", "scp",
                    "-o", "StrictHostKeyChecking=accept-new",
                    "admin@DESKTOP-59B42HE.local:sesame_export/modbot_full.step", dst],
                   check=True)
    print("已拉回 %s (%.1f MB)" % (os.path.relpath(dst),
                                  os.path.getsize(dst) / 1e6))


if __name__ == "__main__":
    main()
