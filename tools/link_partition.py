#!/usr/bin/env python3
"""从 structure.json 计算刚体链划分(union-find),输出 links.json。

节点粒度:舵机拆成 body/arm_double 两个节点(被 revolute 分开),
其余顶层 occurrence 各一个节点。边 = rigid 关节。
未被任何关节约束的孤立顶层件默认归入 body 链(物理上装在机身上)。
"""
import json
import os
import re

D = os.path.join(os.path.dirname(__file__), "..", "simulation", "fusion_export")
data = json.load(open(os.path.join(D, "structure.json")))


def node(path):
    """把任意 occurrence 路径归一化成刚体节点名。"""
    top = path.split("+")[0]
    if top.startswith("DM-S0020"):
        n = re.search(r":(\d+)", top).group(1)
        if "arm_double" in path:
            return f"S{n}.arm"
        return f"S{n}.body"          # body:1 或壳上其它子件
    return top


parent = {}


def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(a, b):
    parent[find(a)] = find(b)


tops = sorted({p.split("+")[0] for p in data["occs"]})
for t in tops:
    if t.startswith("DM-S0020"):
        n = re.search(r":(\d+)", t).group(1)
        find(f"S{n}.body")
        find(f"S{n}.arm")
    else:
        find(t)

rigid_pairs = []
for j in data["joints"]:
    if j["type"] != "revolute" and not j["suppressed"]:
        a, b = node(j["occ1"]), node(j["occ2"])
        rigid_pairs.append((j["name"], a, b))
        union(a, b)

print("rigid edges:")
for name, a, b in rigid_pairs:
    print(f"  {name}: {a} <-> {b}")

# 接地件互相并链(Fusion 里它们各自独立接地,"地"即机身)
ground_nodes = sorted({node(p) for p in data["grounded"]})
for g in ground_nodes[1:]:
    union(g, ground_nodes[0])
body_root = find(ground_nodes[0])

# 孤立件(没进任何 rigid/revolute 关系)归 body
rev_nodes = set()
for j in data["joints"]:
    if j["type"] == "revolute":
        rev_nodes |= {node(j["occ1"]), node(j["occ2"])}
for t in list(parent):
    if find(t) == t and t not in rev_nodes and find(t) != body_root:
        # 单元素集合且不含 revolute 端点 → 孤立电子件
        members = [k for k in parent if find(k) == t]
        if len(members) == 1:
            union(t, body_root)

groups = {}
for k in parent:
    groups.setdefault(find(k), []).append(k)

# 命名:接地链=body;含 hip_XX:1 的=upper_XX;含 F-*(小腿)的=lower_XX
F_LEG = {"F-L3:1": "lf", "F-L4:1": "lr", "F-R3:1": "rf", "F-R4:1": "rr"}
link_names = {find(body_root): "body"}
for t in tops:
    if t.startswith("hip_"):
        link_names.setdefault(find(t), "upper_" + t[4:6])
    if t in F_LEG:
        link_names.setdefault(find(t), "lower_" + F_LEG[t])

links = {}
for root, members in groups.items():
    links[link_names.get(root, "UNNAMED_" + root)] = sorted(members)

print("\nlinks:")
for name, members in sorted(links.items()):
    print(f"  {name}: {members}")

json.dump(links, open(os.path.join(D, "links.json"), "w"), indent=1, ensure_ascii=False)
print(f"\n已存 {os.path.relpath(os.path.join(D, 'links.json'))}")
