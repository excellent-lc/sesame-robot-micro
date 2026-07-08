#!/usr/bin/env python3
"""FreeCAD 直连桥:绕过 MCP,直接调 FreeCADMCP 插件的 XML-RPC(localhost:9875)。

前提:FreeCAD GUI 在运行且 MCP 工作台的 RPC 服务已启动(和 MCP 用同一个插件)。

用法:
  python3 tools/fc_rpc.py -c 'print(FreeCAD.ActiveDocument.Name)'   # 单行代码
  python3 tools/fc_rpc.py 某脚本.py                                  # 整个文件
  python3 tools/fc_rpc.py --async 某脚本.py                          # 重型OCCT布尔用异步

约定(省 token):
  - 代码里只 print 紧凑 JSON/摘要,别倾倒全属性
  - 读用户点选: FreeCADGui.Selection.getSelectionEx()
  - 复用函数放文件里,RPC 端 exec(open('/home/lxy/...').read()) 加载(沙箱看得见 home)

坑:
  - RPC 9875 单实例:已有 FreeCAD 开着时新起实例的 RPC 会落到旧实例上——先探端口复用活实例
  - 无头批处理走 flatpak run --command=freecadcmd org.freecad.FreeCAD 脚本.py
    (沙箱看不到 /tmp,用 home 路径;print 必须 ASCII)
  - 无头保存的 FCStd 全部 Visibility=False、关节 ViewProvider 缺失 -> GUI 跑一次 fc_gui_fixup.py
"""
import sys
import xmlrpc.client

RPC = "http://127.0.0.1:9875"


def main():
    args = sys.argv[1:]
    use_async = "--async" in args
    if use_async:
        args.remove("--async")
    if not args:
        sys.exit(__doc__)
    code = args[1] if args[0] == "-c" else open(args[0]).read()

    srv = xmlrpc.client.ServerProxy(RPC, allow_none=True)
    r = srv.execute_code_async(code) if use_async else srv.execute_code(code)

    msg = r.get("message", "")
    out = msg.split("Output: ", 1)[-1] if "Output: " in msg else msg
    print(out, end="" if out.endswith("\n") else "\n")
    sys.exit(0 if r.get("success") else 1)


if __name__ == "__main__":
    main()
