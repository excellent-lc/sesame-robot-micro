#!/usr/bin/env python3
"""Fusion 直连桥:调局域网 Windows 上的 Fusion MCP 插件(JSON-RPC, execute_api_script)。

前提:Windows(DESKTOP-59B42HE)上 Fusion 已启动且 MCP 插件在跑(localhost:9100,
portproxy 已映射 0.0.0.0:19100 -> 127.0.0.1:9100)。笔记本必须插电,否则 10 分钟睡眠。

用法:
  python3 tools/fusion_rpc.py 某脚本.py                    # 整个文件(须含 def run(context):)
  python3 tools/fusion_rpc.py -c 'print(app.activeDocument.name)'   # 单行,自动包 run()
  python3 tools/fusion_rpc.py -t 300 某脚本.py             # 自定义超时(秒,默认 180)

-c 模式自动注入: adsk.core/adsk.fusion/json/math 已 import,
app/ui/des(Design)/root(rootComponent) 已就绪。

约定(省 token):
  - 脚本里只 print 紧凑 JSON/摘要,别倾倒全属性;输出必须 ASCII(ensure_ascii=True)
  - 一次调用 = 一个事务:未捕获异常回滚本次全部操作 -> 危险操作拆多次调用,逐步验证
  - 重操作 HTTP 响应可能丢失但脚本已执行 -> 用只读查询确认,别盲目重发
  - 读用户点选: ui.activeSelections(执行脚本可能清空选择集,先存关键几何数据)
  - transform2 按世界系读写;改动不进撤销栈,动前先记录 asArray() 备份
  - 单位一律 cm(STL/URDF 是 mm);moveToComponent 只在直接模式,AsBuiltJointInput 只在参数化模式
  - 链接组件子 occurrence 位置会被 删关节/切模式/求解重算 弹回默认姿态 -> 破坏性操作前
    全量记录位姿("位置保险箱"),漂移用 setWithArray 自顶向下重放;接地接壳子件,别接 wrapper
"""
import argparse
import json
import os
import sys
import urllib.request

MCP_URL = os.environ.get("FUSION_MCP_URL", "http://DESKTOP-59B42HE.local:19100/")

WRAP = """import adsk.core, adsk.fusion, json, math

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
{body}
"""


def call_fusion(script, timeout=180):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "execute_api_script",
                          "arguments": {"script": script}}}
    req = urllib.request.Request(MCP_URL, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    if "error" in resp:
        # 插件侧 ~30s 看门狗:超时返回 error 但脚本可能仍在执行,勿盲目重发重操作
        raise RuntimeError("fusion-mcp error: %s" % resp["error"].get("message"))
    res = resp["result"]
    if "content" not in res:
        raise RuntimeError("fusion-mcp unexpected result: %s" % json.dumps(res)[:600])
    return "\n".join(c.get("text", "") for c in res["content"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?", help="Fusion API 脚本文件(含 def run(context):)")
    ap.add_argument("-c", "--code", help="单行/多行代码,自动包进 run(context)")
    ap.add_argument("-t", "--timeout", type=int, default=180, help="HTTP 超时秒数")
    args = ap.parse_args()

    if args.code:
        body = "\n".join("    " + ln for ln in args.code.splitlines())
        script = WRAP.format(body=body)
    elif args.script:
        script = open(args.script).read()
        if "def run(" not in script:
            sys.exit("脚本缺少 def run(context): 入口")
    else:
        ap.print_help()
        sys.exit(1)

    out = call_fusion(script, args.timeout)
    print(out, end="" if out.endswith("\n") else "\n")


if __name__ == "__main__":
    main()
