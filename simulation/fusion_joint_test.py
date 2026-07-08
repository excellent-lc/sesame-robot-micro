#!/usr/bin/env python3
"""Fusion 关节测试:让当前装配里的 revolute 关节各“动一下”再回原位。

通过 Fusion MCP 插件(JSON-RPC, execute_api_script)远程驱动:
  1. 只读列出所有关节(joints + asBuiltJoints)及当前角度
  2. 记录全部 occurrence 的 transform2(位置保险箱,防回弹漂移)
  3. 逐个 revolute 关节 ±AMP 度摆动后回到原角度(每个关节一次独立调用)
  4. 只读对账:关节角度已还原、occurrence 位姿无漂移

用法:
  python3 fusion_joint_test.py               # 全部 revolute 关节各动一下
  python3 fusion_joint_test.py --list        # 只列关节,不动
  python3 fusion_joint_test.py --joint 名字  # 只动指定关节(可重复传)
  python3 fusion_joint_test.py --amp 30      # 摆幅 30 度(默认 15)
"""
import argparse
import json
import math
import os
import sys
import urllib.request

MCP_URL = os.environ.get("FUSION_MCP_URL", "http://DESKTOP-59B42HE.local:19100/")


def call_fusion(script, timeout=120):
    """调 execute_api_script,返回脚本 print 出来的 JSON(dict);失败返回 None。"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "execute_api_script", "arguments": {"script": script}},
    }
    req = urllib.request.Request(
        MCP_URL, json.dumps(payload).encode(), {"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.load(r)
    except Exception as e:  # 重操作时 HTTP 响应可能丢失,但脚本多半已执行
        print(f"  [warn] HTTP 异常({e}),稍后用只读查询对账", file=sys.stderr)
        return None
    texts = [c.get("text", "") for c in resp.get("result", {}).get("content", [])]
    raw = "\n".join(texts)
    # print 输出可能混在插件的包装文字里,取第一个 { 到最后一个 } 之间解析
    a, b = raw.find("{"), raw.rfind("}")
    if a == -1 or b <= a:
        print(f"  [warn] 无法解析返回: {raw[:300]!r}", file=sys.stderr)
        return None
    try:
        return json.loads(raw[a : b + 1])
    except json.JSONDecodeError:
        print(f"  [warn] 返回不是 JSON: {raw[:300]!r}", file=sys.stderr)
        return None


# ---------- Fusion 侧脚本模板(不用 f-string,避免大括号转义) ----------

LIST_SCRIPT = """
import adsk.core, adsk.fusion, json, math

def run(context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    out = {"doc": app.activeDocument.name,
           "parametric": des.designType == adsk.fusion.DesignTypes.ParametricDesignType,
           "joints": []}
    colls = [getattr(root, "allJoints", root.joints),
             getattr(root, "allAsBuiltJoints", root.asBuiltJoints)]
    for coll in colls:
        for j in coll:
            item = {"name": j.name, "suppressed": j.isSuppressed}
            rev = adsk.fusion.RevoluteJointMotion.cast(j.jointMotion)
            if rev:
                item["type"] = "revolute"
                item["deg"] = round(math.degrees(rev.rotationValue), 4)
            else:
                item["type"] = j.jointMotion.objectType.split("::")[-1]
            out["joints"].append(item)
    print(json.dumps(out, ensure_ascii=False))
"""

POSES_SCRIPT = """
import adsk.core, adsk.fusion, json

def run(context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    out = {}
    for occ in des.rootComponent.allOccurrences:
        out[occ.fullPathName] = list(occ.transform2.asArray())
    print(json.dumps({"poses": out}))
"""

WIGGLE_SCRIPT = """
import adsk.core, adsk.fusion, json, math

TARGET = __TARGET__
AMP = math.radians(__AMP__)
STEPS = 6

def run(context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    colls = [getattr(root, "allJoints", root.joints),
             getattr(root, "allAsBuiltJoints", root.asBuiltJoints)]
    joint = None
    for coll in colls:
        for j in coll:
            if j.name == TARGET:
                joint = j
    if joint is None:
        print(json.dumps({"error": "joint not found", "name": TARGET}))
        return
    rev = adsk.fusion.RevoluteJointMotion.cast(joint.jointMotion)
    if rev is None:
        print(json.dumps({"error": "not revolute", "name": TARGET}))
        return
    start = rev.rotationValue
    seq = []
    for i in range(1, STEPS + 1):            # 0 -> +AMP
        seq.append(start + AMP * i / STEPS)
    for i in range(1, 2 * STEPS + 1):        # +AMP -> -AMP
        seq.append(start + AMP - 2 * AMP * i / (2 * STEPS))
    for i in range(1, STEPS + 1):            # -AMP -> 0
        seq.append(start - AMP + AMP * i / STEPS)
    for v in seq:
        rev.rotationValue = v
        adsk.doEvents()
        app.activeViewport.refresh()
    rev.rotationValue = start
    adsk.doEvents()
    app.activeViewport.refresh()
    print(json.dumps({"joint": joint.name,
                      "startDeg": round(math.degrees(start), 4),
                      "endDeg": round(math.degrees(rev.rotationValue), 4),
                      "restored": abs(rev.rotationValue - start) < 1e-9}))
"""


def main():
    ap = argparse.ArgumentParser(description="Fusion revolute 关节摆动测试")
    ap.add_argument("--list", action="store_true", help="只列关节,不动")
    ap.add_argument("--joint", action="append", help="只测指定关节(可重复)")
    ap.add_argument("--amp", type=float, default=15.0, help="摆幅(度),默认 15")
    args = ap.parse_args()

    print(f"连接 {MCP_URL}")
    info = call_fusion(LIST_SCRIPT, timeout=30)
    if info is None:
        sys.exit("无法获取关节列表,检查 Fusion / portproxy / 插件是否在跑")
    print(f"文档: {info['doc']}  参数化模式: {info['parametric']}")
    revolutes = [j for j in info["joints"] if j["type"] == "revolute" and not j["suppressed"]]
    print(f"关节共 {len(info['joints'])} 个,其中可动 revolute {len(revolutes)} 个:")
    for j in revolutes:
        print(f"  {j['name']:30s} 当前 {j['deg']:8.3f}°")
    if args.list:
        return
    if not info["parametric"]:
        sys.exit("当前是直接建模模式,关节无法驱动,请切回参数化模式")

    targets = args.joint or [j["name"] for j in revolutes]

    print("\n记录位姿保险箱 ...")
    before = call_fusion(POSES_SCRIPT, timeout=60)
    if before is None:
        sys.exit("位姿记录失败,中止(不做任何移动)")
    vault = before["poses"]
    print(f"  已记录 {len(vault)} 个 occurrence")

    print(f"\n逐个摆动 ±{args.amp}° ...")
    for name in targets:
        script = WIGGLE_SCRIPT.replace("__TARGET__", json.dumps(name)).replace(
            "__AMP__", repr(args.amp)
        )
        r = call_fusion(script, timeout=180)
        if r is None:
            print(f"  {name}: 响应丢失(脚本可能已执行)")
        elif "error" in r:
            print(f"  {name}: 失败 - {r['error']}")
        else:
            ok = "已回原位" if r["restored"] else f"!! 未还原 end={r['endDeg']}°"
            print(f"  {name}: {r['startDeg']}° -> ±{args.amp}° -> {r['endDeg']}°  {ok}")

    print("\n对账位姿 ...")
    after = call_fusion(POSES_SCRIPT, timeout=60)
    if after is None:
        sys.exit("对账查询失败,请手动检查模型位姿")
    drifted = []
    for path, m0 in vault.items():
        m1 = after["poses"].get(path)
        if m1 is None:
            drifted.append((path, "missing"))
            continue
        d = max(abs(a - b) for a, b in zip(m0, m1))
        if d > 1e-6:
            drifted.append((path, f"drift {d:.6g}"))
    if drifted:
        print(f"!! 检测到 {len(drifted)} 个 occurrence 漂移:")
        for path, why in drifted[:20]:
            print(f"  {path}: {why}")
        sys.exit(1)
    print(f"全部 {len(vault)} 个 occurrence 位姿无漂移,测试通过 ✔")


if __name__ == "__main__":
    main()
