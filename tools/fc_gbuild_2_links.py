"""GUI 重建 phase2:顶层映射 -> 舵机拆分 -> Assembly + 9 链容器。经 fc_rpc 执行。"""
import FreeCAD
import json

REPO = "/home/lxy/Desktop/work/sesame-robot-micro"
structure = json.load(open(REPO + "/simulation/fusion_export/structure.json"))
links = json.load(open(REPO + "/simulation/fusion_export/links.json"))

doc = FreeCAD.getDocument("SesameMicro")
V = FreeCAD.Vector

root = [o for o in doc.Objects if not o.InList and o.TypeId == "App::Part"][0]
tops = list(root.Group)

def occ_t(p):
    t = structure["occs"][p]["transform"]
    return V(t[3] * 10, t[7] * 10, t[11] * 10)

fusion_tops = sorted({p.split("+")[0] for p in structure["occs"]})
servo_occs = [t for t in fusion_tops if t.startswith("DM-S0020")]
PREFIX = [("SPDT", "SPDT Mini Slide Switch:1"),
          ("Seeed Studio XIAO", "Seeed Studio XIAO-ESP32-C3:1"),
          ("Waveshare", "Waveshare 1315 0.49in i2c 64x32 oled display v1:1"),
          ("proto-board", "proto-board:1"),
          ("hip_lf", "hip_lf:1"), ("hip_lr", "hip_lr:1"),
          ("hip_rf", "hip_rf:1"), ("hip_rr", "hip_rr:1"),
          ("F-L3", "F-L3:1"), ("F-L4", "F-L4:1"),
          ("F-R3", "F-R3:1"), ("F-R4", "F-R4:1"),
          ("COMPOUND", "COMPOUND:root")]
name_map, unmatched = {}, []
for obj in tops:
    lab = obj.Label
    if lab.startswith("DM-S0020"):
        best, bestd = None, 1e9
        for occ in servo_occs:
            d = (obj.Placement.Base - occ_t(occ)).Length
            if d < bestd:
                best, bestd = occ, d
        if bestd > 0.1 or best in name_map:
            unmatched.append(lab)
            continue
        name_map[best] = obj
    else:
        for pref, occ in PREFIX:
            if lab.startswith(pref):
                name_map[occ] = obj
                break
        else:
            unmatched.append(lab)
assert len(name_map) >= 20 and not unmatched, "mapping bad: %s" % unmatched
if "COMPOUND:root" in name_map:
    links["body"] = links["body"] + ["COMPOUND:root"]

servo_feat = {}
for occ, part in name_map.items():
    if not occ.startswith("DM-S0020"):
        continue
    n = occ.split(":")[1]
    feats = [c for c in part.Group if c.TypeId == "Part::Feature"]
    body = [f for f in feats if "arm" not in f.Label.lower()]
    arm = [f for f in feats if "arm" in f.Label.lower()]
    assert len(body) == 1 and len(arm) == 1, occ
    for key, f in (("S%s.body" % n, body[0]), ("S%s.arm" % n, arm[0])):
        f.Label = key.replace(".", "_")
        servo_feat[key] = (f, part.Placement * f.Placement)

asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
jg = doc.addObject("Assembly::JointGroup", "Joints")
asm.addObject(jg)
link_obj = {}
for lname, members in links.items():
    lp = doc.addObject("App::Part", "link_" + lname)
    lp.Label = lname
    asm.addObject(lp)
    link_obj[lname] = lp
    for m in members:
        if m in servo_feat:
            f, gplc = servo_feat[m]
            lp.addObject(f)
            f.Placement = gplc
        else:
            lp.addObject(name_map[m])

def purge(obj):
    kids = [c for c in obj.OutList if c.TypeId.startswith("App::Origin")
            or c.TypeId in ("App::Line", "App::Plane", "App::Point")]
    doc.removeObject(obj.Name)
    for k in kids:
        try:
            doc.removeObject(k.Name)
        except Exception:
            pass

for occ in servo_occs:
    purge(name_map[occ])
purge(root)
doc.recompute()
labels = sorted(lp.Label for lp in link_obj.values())
assert labels == sorted(links), labels
print(json.dumps({"links": labels}))
