#!/usr/bin/env python3
"""Fusion → FreeCAD 一键转换流水线(总编排器)。

前提:
  - Windows 上 Fusion 打开 Modbot 文档(插件 HTTP DESKTOP-59B42HE.local:19100)
  - 本机 FreeCAD GUI 打开(FreeCADMCP RPC 127.0.0.1:9875,auto_start 已开)

步骤(可用 --from N 从第 N 步续跑):
  1 dump-structure   关节/刚组/接地/位姿 -> structure.json
  2 partition        刚体链划分 -> links.json
  3 dump-physical    质量/质心/惯量/材料 -> physical.json
  4 export-step      全量 STEP(临时显示隐藏体)-> modbot_full.step
  5 build-freecad    GUI 三阶段构建 + 改名存盘 -> hardware/CAD/Sesame-Micro.FCStd
  6 verify           逐关节摆动 + 位姿对账

产物全在 simulation/fusion_export/ 与 hardware/CAD/。

转换坑速查:
  - Fusion STEP 导出跳过隐藏 body(export-step 已临时 isLightBulbOn=True 再恢复)
  - 颜色必须 GUI ImportGui.insert 才保留,无头 Import 全丢;渲染材质 STEP 不携带
  - Fusion 根级散装 body 进 STEP 变 COMPOUNDxxx,phase4 按 physicalProperties.volume 对体积恢复真名
  - FreeCAD Assembly 关节:先 jg.addObject(jt) 再 JointObject.Joint(jt,1);
    引用双空子路径 (链Part, ["",""]);建关节时关自动求解 SolveInJointCreation=False
  - 动画/回放必须全链 FK 指令,不能只动一链让 solver 带(未指令自由度会漂移)
  - 反向(FreeCAD→Fusion)无流水线:走 STEP 导出 + Fusion 端上传,结构/关节需重建
"""
import argparse
import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd, **kw):
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=HERE, **kw)


def rpc_alive():
    try:
        socket.create_connection(("127.0.0.1", 9875), 2).close()
        return True
    except OSError:
        return False


STEPS = [
    ("dump-structure", [sys.executable, "fusion_dump_structure.py"]),
    ("partition",      [sys.executable, "link_partition.py"]),
    ("dump-physical",  [sys.executable, "fusion_dump_physical.py"]),
    ("export-step",    [sys.executable, "fusion_export_step.py"]),
    ("build-freecad",  None),   # 特殊处理:四个 fc_rpc 阶段
    ("verify",         [sys.executable, "fc_joint_wiggle_gui.py"]),
]


def main():
    ap = argparse.ArgumentParser(description="Fusion -> FreeCAD 一键转换")
    ap.add_argument("--from", dest="start", type=int, default=1,
                    help="从第 N 步开始(默认 1)")
    ap.add_argument("--until", type=int, default=len(STEPS), help="跑到第 N 步为止")
    args = ap.parse_args()

    for i, (name, cmd) in enumerate(STEPS, 1):
        if not (args.start <= i <= args.until):
            continue
        print("\n===== step %d/%d: %s =====" % (i, len(STEPS), name))
        if name == "build-freecad":
            if not rpc_alive():
                sys.exit("FreeCAD GUI 没开(RPC 9875 不通)。请先启动:\n"
                         "  flatpak run org.freecad.FreeCAD")
            for phase in ("fc_gbuild_1_import.py", "fc_gbuild_2_links.py",
                          "fc_gbuild_3_joints.py", "fc_gbuild_4_finish.py"):
                run([sys.executable, "fc_rpc.py", phase])
        else:
            run(cmd)
    print("\n流水线完成。")


if __name__ == "__main__":
    main()
