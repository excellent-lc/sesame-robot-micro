# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

本文件是 CAD 操控索引：**用法细节和坑全在各脚本的文档字符串里，用前先读对应脚本头部**。项目/固件内容见 README.md。

## CAD 操控入口

| 场景 | 入口 | 细节 |
|---|---|---|
| Fusion 机械调整（读点选/找件/对面对孔/移动/干涉） | `python3 tools/fusion_tool.py <子命令>` | 脚本头注释 |
| Fusion 自定义脚本 | `python3 tools/fusion_rpc.py -c '...'` 或 `脚本.py` | 脚本头注释（含 API 坑清单） |
| FreeCAD GUI 交互 | `python3 tools/fc_rpc.py -c '...'` | 脚本头注释（含无头/单实例坑） |
| Fusion → FreeCAD 工程转换 | `python3 tools/fusion_to_freecad.py` | 脚本头注释（含转换坑速查） |

Fusion 在局域网 Windows `DESKTOP-59B42HE.local:19100`（须插电防睡眠）；FreeCAD 在本机（RPC :9875 / flatpak 无头）。

## 省 token 纪律

1. **优先级：`fusion_tool.py` 子命令 > 复用 `tools/` 已有脚本 > 写新脚本**。新的通用操作写完就扩展进 `fusion_tool.py` 的 `BODIES` 或收进 `tools/`，别留在 scratchpad 一次性用完
2. **不用 MCP 工具直调**（`mcp__freecad__*` 等），Bash + rpc 桥更省；传输层与 token 无关
3. **验证用数值不用截图**（面间隙/孔同心/干涉体积）；截图仅在用户要看效果时用小分辨率或落盘 scp
4. **输出只 print 紧凑 ASCII JSON**；大 dump 落盘再 scp，stdout 只打摘要
5. **多轮摸索交给 subagent**，主上下文只收结论

## 改 Fusion 模型前必读

一次调用 = 一个事务（异常回滚全部）→ 拆成 只读检查 → 改动 → 只读验证；transform2 改动不进撤销栈，动前记 `asArray()` 备份。其余坑见 `tools/fusion_rpc.py` 头注释。
