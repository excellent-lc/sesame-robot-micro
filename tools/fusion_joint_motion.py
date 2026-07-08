#!/usr/bin/env python3
"""Fusion 四足运动测试:驱动远端 Fusion 里 8 个 asBuilt revolute 关节做动画。

阶段: 1) 逐关节正弦摆动(hip/knee x 4 腿) 2) 对角步态(lf+rr 与 rf+lr 反相,
髋摆动+膝抬腿) 3) 全部回零并核对根级 occurrence 位姿无漂移。

用法:
  python3 tools/fusion_joint_motion.py                     # 默认:摆动 2s/关节 + 步态 90s @1.4Hz
  python3 tools/fusion_joint_motion.py --dur 120 --freq 2  # 更长更快
  python3 tools/fusion_joint_motion.py --skip-wiggle       # 只跑步态

坑:
  - MCP 插件有 ~30s 工具执行看门狗:超时返回 JSON-RPC error 但脚本可能仍在跑
    -> 动画切成 <=SEG(20)s 的分段调用;步态相位用全局 t0 接续,段间有 ~1s 停顿
  - 看门狗超时后服务器忙 -> ping 轮询等空闲再重发该段(段内容幂等,重发安全)
  - 关节是 asBuiltJoints 不是 joints;AsBuiltJointVector 没有 .count,用 list()/len()
  - rotationValue 单位弧度;限位 +-90 度,振幅别超
  - 每帧 adsk.doEvents() 才重绘视口;正弦相位按墙钟算,帧率波动不影响动作速度
  - pose0 在首段抓取,由本地进程转发到末段在 Fusion 侧比对,stdout 只打摘要
"""
import argparse
import json
import sys
import time

from fusion_rpc import call_fusion

SEG = 20.0  # 每段最大动画秒数,须留出 30s 看门狗余量

SCRIPT = r'''import adsk.core, adsk.fusion, json, math, time

P = json.loads(r"""__PARAMS__""")

def run(context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    D = math.pi / 180.0

    revs = {}
    for coll in (root.allAsBuiltJoints, root.allJoints):
        for j in coll:
            try:
                jm = j.jointMotion
                if jm.jointType == adsk.fusion.JointTypes.RevoluteJointType and not j.isSuppressed:
                    revs[j.name] = jm
            except Exception:
                pass

    legs = ["lf", "rf", "lr", "rr"]
    names = ["hip_%s_rev" % l for l in legs] + ["knee_%s_rev" % l for l in legs]
    missing = [n for n in names if n not in revs]
    if missing:
        print(json.dumps({"err": "joints missing", "missing": missing}))
        return

    out = {}
    if P.get("fit"):
        try:
            app.activeViewport.fit()
        except Exception:
            pass
    if P.get("snap_pose"):
        out["pose0"] = {o.fullPathName: [round(x, 6) for x in o.transform2.asArray()]
                        for o in root.occurrences}

    state = {"frames": 0}
    def anim(dur, set_fn):
        t0 = time.time()
        while True:
            el = time.time() - t0
            if el >= dur:
                break
            set_fn(el)
            adsk.doEvents()
            state["frames"] += 1

    t_start = time.time()
    for w in P.get("wiggle") or []:
        jm = revs[w["name"]]
        wa, ww = w["deg"] * D, 2 * math.pi * w["freq"]
        anim(w["dur"], lambda el, jm=jm: setattr(
            jm, "rotationValue", wa * math.sin(ww * el)))
        jm.rotationValue = 0.0
        adsk.doEvents()

    g = P.get("gait")
    if g:
        ah, ak = g["hip_deg"] * D, g["knee_deg"] * D
        w = 2 * math.pi * g["freq"]
        pha = {"lf": 0.0, "rr": 0.0, "rf": math.pi, "lr": math.pi}
        def gait(el):
            for l in legs:
                th = w * (g["t0"] + el) + pha[l]
                revs["hip_" + l + "_rev"].rotationValue = ah * math.sin(th)
                revs["knee_" + l + "_rev"].rotationValue = ak * 0.5 * (1 - math.cos(th))
        anim(g["dur"], gait)

    if P.get("zero"):
        for n in names:
            revs[n].rotationValue = 0.0
        adsk.doEvents()
        out["resid_deg"] = round(max(abs(revs[n].rotationValue) for n in names) / D, 6)

    if P.get("pose0"):
        drift = 0.0
        for o in root.occurrences:
            a0 = P["pose0"].get(o.fullPathName)
            if a0:
                drift = max(drift, max(abs(x - y) for x, y in
                                       zip(a0, o.transform2.asArray())))
        out["pose_drift"] = round(drift, 9)
        try:
            out["pendingSnapshot"] = bool(des.snapshots.hasPendingSnapshot)
        except Exception:
            pass

    total = time.time() - t_start
    out["sec"] = round(total, 1)
    out["frames"] = state["frames"]
    out["fps"] = round(state["frames"] / max(total, 0.001), 1)
    print(json.dumps(out))
'''


def call_seg(params, anim_sec, label):
    """一段动画;看门狗超时则 ping 等服务器空闲后重发一次。"""
    script = SCRIPT.replace("__PARAMS__", json.dumps(params))
    for attempt in (1, 2):
        try:
            return json.loads(call_fusion(script, int(anim_sec + 40)))
        except Exception as e:
            if attempt == 2:
                sys.exit("段 %s 两次失败: %s" % (label, e))
            print("  ! %s 失败(%s),等服务器空闲后重发" % (label, str(e)[:60]))
            ping = SCRIPT.replace("__PARAMS__", json.dumps({}))
            for _ in range(12):
                try:
                    json.loads(call_fusion(ping, 40))
                    break
                except Exception:
                    time.sleep(8)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dur", type=float, default=90, help="步态时长秒")
    ap.add_argument("--freq", type=float, default=1.4, help="步态频率 Hz")
    ap.add_argument("--hip-deg", type=float, default=25, help="髋摆幅度(度)")
    ap.add_argument("--knee-deg", type=float, default=35, help="膝抬腿幅度(度,单向)")
    ap.add_argument("--wiggle-dur", type=float, default=2.0, help="逐关节摆动秒/关节")
    ap.add_argument("--wiggle-freq", type=float, default=2.0, help="逐关节摆动 Hz")
    ap.add_argument("--wiggle-deg", type=float, default=35, help="逐关节摆动幅度(度)")
    ap.add_argument("--skip-wiggle", action="store_true")
    a = ap.parse_args()

    legs = ["lf", "rf", "lr", "rr"]
    names = ["hip_%s_rev" % l for l in legs] + ["knee_%s_rev" % l for l in legs]

    # 首段:抓 pose0 + 调视角(不动画,秒回)
    r = call_seg({"fit": True, "snap_pose": True}, 0, "init")
    pose0 = r["pose0"]
    print("初始化: %d 个根级 occurrence 位姿已存,视角已 fit" % len(pose0))

    if not a.skip_wiggle:
        per_call = max(1, int(SEG // a.wiggle_dur))
        for i in range(0, len(names), per_call):
            grp = names[i:i + per_call]
            wig = [{"name": n, "dur": a.wiggle_dur, "deg": a.wiggle_deg,
                    "freq": a.wiggle_freq} for n in grp]
            r = call_seg({"wiggle": wig}, len(grp) * a.wiggle_dur,
                         "wiggle[%s..]" % grp[0])
            print("  摆动 %-12s.. %d关节 %.1fs %dfps" % (grp[0], len(grp),
                                                        r["sec"], r["fps"]))

    t0, done = 0.0, 0.0
    nseg = max(1, int(-(-a.dur // SEG)))
    for i in range(nseg):
        seg = min(SEG, a.dur - done)
        last = (i == nseg - 1)
        params = {"gait": {"t0": t0, "dur": seg, "freq": a.freq,
                           "hip_deg": a.hip_deg, "knee_deg": a.knee_deg}}
        if last:
            params["zero"] = True
            params["pose0"] = pose0
        r = call_seg(params, seg, "gait%d" % (i + 1))
        done += seg
        t0 += seg
        msg = "  步态 %2d/%d  %.0f/%.0fs  %dfps" % (i + 1, nseg, done, a.dur, r["fps"])
        if last:
            msg += "  回零残差%.4f度 位姿漂移%.2e" % (r["resid_deg"], r["pose_drift"])
            if r.get("pendingSnapshot"):
                msg += " (pendingSnapshot)"
        print(msg)

    ok = r["resid_deg"] < 1e-3 and r["pose_drift"] < 1e-6
    print("运动测试%s: 8关节摆动 + %.0fs对角步态@%.1fHz" % ("通过" if ok else "!!异常", a.dur, a.freq))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
