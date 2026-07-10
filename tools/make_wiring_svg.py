#!/usr/bin/env python3
"""生成 hardware/wiring.svg — Sesame Robot Micro 接线图(XIAO ESP32-S3 · 1S 直供)。

用法:
    python3 tools/make_wiring_svg.py          # 重新生成 hardware/wiring.svg

依据:
  - hardware/BOM.md §3 供电拓扑: 1S LiPo → SPDT 开关 → V+ 轨(集线板) →
    XIAO 背面 B+/B− 直焊 + 8×舵机 V+;全机共地;无 DC-DC。
  - 固件 main-board-firmware/mini-firmware.ino: 8 通道舵机(CH0-3=髋 stand=135/45/45/135,
    CH4-7=腿 stand=0/180)、SSD1306 I²C 0x3C。
  - XIAO ESP32-S3 引脚(官方 wiki): D0-D3=GPIO1-4, D4=SDA/GPIO5, D5=SCL/GPIO6,
    D6=TX/GPIO43(留空,boot 日志会抖舵机), D7=RX/GPIO44, D8-D10=GPIO7/8/9。
  - 通道→引脚映射(本图定义,固件移植时用): servoPins={1,2,3,4,9,8,7,44} (GPIO),
    即 CH0-3=D0-D3(髋), CH4-7=D10,D9,D8,D7(腿)。

嵌入图片(hardware/img/, 来源 Seeed 官方 wiki, 下载后已缩裁):
  - xiao-esp32s3-pinout-front.jpg  官方正面引脚图
    https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/img/2.jpg
  - xiao-bat-pads-solder.jpg       官方 1S 电池直焊背面 B+/B− 示例
    https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/img/16.jpg

布线规则(改坐标前必读, 否则会交叉):
  - 全部正交折线。信号扇出遵循"车道"法则: XIAO 全部位于集线板列的左/下方,
    列越靠右 → 水平车道(lane)越低(y 越大);竖直上升段(riser)在焊盘出线一侧
    从内到外与焊盘顺序一致。改列/焊盘坐标后必须重新目检(headless chrome 截图)。
  - OLED 的 GND/3V3 引脚被 D7-D10 信号束围住,电气上无法平面化 → 两根电源线
    用"拱桥"(hop)一次跨过 4 根信号 riser;红色 B+ 馈线跨黑色主线同理。
"""

import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "hardware", "img")
OUT = os.path.join(ROOT, "hardware", "wiring.svg")

W, H = 1920, 1080
FONT = "Noto Sans CJK SC, PingFang SC, Microsoft YaHei, sans-serif"
MONO = "JetBrains Mono, Consolas, monospace"

C_RED = "#e02020"      # V+ (电池轨 3.0-4.2V)
C_BLK = "#1a1a1a"      # GND
C_SIG = "#f5a623"      # 舵机信号
C_SCL = "#5cb832"      # I2C SCL
C_SDA = "#2196f3"      # I2C SDA
C_PCB = "#1f9d55"      # 洞洞板绿
C_BOARD = "#241f26"    # XIAO PCB 黑
C_PAD = "#e6c34a"      # 焊盘金
C_TXT = "#222"
C_GRAY = "#777"

svg = []


def add(s):
    svg.append(s)


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def elbow(pts, r=12):
    """正交折线 → 带圆角的 path d 字符串。"""
    d = [f"M {pts[0][0]} {pts[0][1]}"]
    for i in range(1, len(pts) - 1):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        dx1 = (x1 - x0) and (1 if x1 > x0 else -1)
        dy1 = (y1 - y0) and (1 if y1 > y0 else -1)
        dx2 = (x2 - x1) and (1 if x2 > x1 else -1)
        dy2 = (y2 - y1) and (1 if y2 > y1 else -1)
        seg1 = abs(x1 - x0) + abs(y1 - y0)
        seg2 = abs(x2 - x1) + abs(y2 - y1)
        rr = min(r, seg1 / 2, seg2 / 2)
        d.append(f"L {x1 - dx1 * rr} {y1 - dy1 * rr}")
        d.append(f"Q {x1} {y1} {x1 + dx2 * rr} {y1 + dy2 * rr}")
    d.append(f"L {pts[-1][0]} {pts[-1][1]}")
    return " ".join(d)


def wire(pts, color, w=3.5, r=12, dash=None):
    dd = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<path d="{elbow(pts, r)}" fill="none" stroke="{color}" '
        f'stroke-width="{w}" stroke-linecap="round"{dd}/>')


def raw_wire(d, color, w=3.5):
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" '
        f'stroke-linecap="round"/>')


def dot(x, y, color):
    add(f'<circle cx="{x}" cy="{y}" r="4.5" fill="{color}"/>')


def text(x, y, s, size=13, color=C_TXT, weight="normal", anchor="start", font=FONT):
    add(f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
        f'fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{esc(s)}</text>')


def b64img(fname):
    p = os.path.join(IMG_DIR, fname)
    mime = "image/png" if fname.endswith(".png") else "image/jpeg"
    with open(p, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


# ============================================================ 画布
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

# ============================================================ 标题 + 图例
text(50, 72, "Sesame Robot Micro", 34, "#111", "bold")
text(50, 106, "接线图 · XIAO ESP32-S3 · 1S 直供(无 DC-DC)", 20, "#8b3fc6", "bold")
legend = [(C_RED, "红 V+ 3.0–4.2V"), (C_BLK, "黑 GND"), (C_SIG, "橙 舵机信号"),
          (C_SCL, "绿 SCL"), (C_SDA, "蓝 SDA")]
lx = 50
for c, label in legend:
    add(f'<line x1="{lx}" y1="140" x2="{lx + 26}" y2="140" stroke="{c}" '
        f'stroke-width="5" stroke-linecap="round"/>')
    text(lx + 32, 145, label, 13, C_TXT)
    lx += 32 + len(label) * 12 + 26
text(50, 168, "依据 hardware/BOM.md §3 · 生成: tools/make_wiring_svg.py", 11, C_GRAY)

# ============================================================ 右上: 官方参考图
pin_img = b64img("xiao-esp32s3-pinout-front.jpg")
bat_img = b64img("xiao-bat-pads-solder.jpg")
add('<rect x="1246" y="46" width="348" height="164" rx="10" fill="none" '
    'stroke="#e8833a" stroke-width="3"/>')
add(f'<image x="1250" y="50" width="340" height="156" href="{pin_img}"/>')
text(1250, 226, "官方引脚图 (Seeed Wiki)", 12, C_GRAY)
add('<rect x="1636" y="46" width="198" height="198" rx="10" fill="none" '
    'stroke="#e8833a" stroke-width="3"/>')
add(f'<image x="1640" y="50" width="190" height="190" href="{bat_img}"/>')
text(1640, 262, "官方示例: 1S 直焊背面 B+/B−", 12, C_GRAY)

# ============================================================ 电池
add('<rect x="70" y="180" width="230" height="140" rx="12" fill="#c8cdd4" '
    'stroke="#8d939c" stroke-width="3"/>')
add('<rect x="82" y="192" width="206" height="116" rx="8" fill="#dde1e6"/>')
text(185, 232, "1S LiPo 3.7V · ≥25C", 20, "#111", "bold", "middle")
text(185, 256, "102050 · 600–1000mAh", 13, "#333", "normal", "middle")
text(185, 278, "无 PCM → 固件低压切断 (P1)", 12, C_RED, "bold", "middle")
text(185, 298, "≥25C 预留无人机 · PH2.0/直焊", 11, C_GRAY, "normal", "middle")
add(f'<rect x="296" y="196" width="12" height="18" fill="{C_RED}"/>')
add(f'<rect x="296" y="291" width="12" height="18" fill="{C_BLK}"/>')
text(316, 212, "+", 18, C_RED, "bold")
text(316, 306, "−", 18, C_BLK, "bold")

# ============================================================ 开关 + 电源主线
text(398, 192, "SS-12D00 滑动开关 (P2)", 12, C_TXT, "bold")
add('<rect x="400" y="205" width="90" height="52" rx="6" fill="#3a3a3a" '
    'stroke="#111" stroke-width="2"/>')
add('<rect x="412" y="217" width="66" height="14" rx="3" fill="#666"/>')
add('<rect x="418" y="213" width="20" height="22" rx="3" fill="#ddd"/>')
text(445, 249, "ON→", 11, "#eee")
# 电池+ → 开关 → V+ 轨入口(集线板)
wire([(300, 205), (360, 205), (360, 231), (400, 231)], C_RED)
wire([(490, 231), (700, 231), (700, 490), (768, 490)], C_RED)
# 电池− → GND 轨入口
wire([(300, 300), (660, 300), (660, 440), (768, 440)], C_BLK)
# B+ 馈线: 从开关输出分支 → XIAO 背面 B+ (x520 竖线, 在 y300 拱过黑色主线)
dot(520, 231, C_RED)
raw_wire("M 520 231 L 520 292 A 8 8 0 0 0 520 308 L 520 1015 L 688 1015", C_RED)
# B− 馈线: 从电池−分支 → XIAO 背面 B−
dot(505, 300, C_BLK)
wire([(505, 300), (505, 1032), (768, 1032), (768, 1022)], C_BLK)

# ============================================================ 集线板 (洞洞板)
BX0, BY0, BX1, BY1 = 750, 395, 1210, 585
ROW_GND, ROW_VP, ROW_SIG = 440, 490, 540
COLS = [800, 848, 896, 944, 992, 1040, 1088, 1136]
CH_INFO = [  # (通道, 关节, XIAO引脚)
    ("CH0", "髋1", "D0"), ("CH1", "髋2", "D1"),
    ("CH2", "髋3", "D2"), ("CH3", "髋4", "D3"),
    ("CH4", "腿1", "D10"), ("CH5", "腿2", "D9"),
    ("CH6", "腿3", "D8"), ("CH7", "腿4", "D7"),
]
text(915, 380, "集线板 (W2): 洞洞板剪裁 ≈43×15mm · 8 列×3 排排针", 15, C_TXT, "bold")
add(f'<rect x="{BX0}" y="{BY0}" width="{BX1 - BX0}" height="{BY1 - BY0}" rx="10" '
    f'fill="{C_PCB}" stroke="#14713c" stroke-width="3"/>')
for hy in range(BY0 + 18, BY1 - 10, 24):
    for hx in range(BX0 + 22, BX1 - 12, 24):
        add(f'<circle cx="{hx}" cy="{hy}" r="2.2" fill="#0f5c30"/>')
# 汇流排(GND/V+)
add(f'<line x1="{BX0 + 15}" y1="{ROW_GND}" x2="{BX1 - 15}" y2="{ROW_GND}" '
    f'stroke="{C_BLK}" stroke-width="6" stroke-linecap="round"/>')
add(f'<line x1="{BX0 + 15}" y1="{ROW_VP}" x2="{BX1 - 15}" y2="{ROW_VP}" '
    f'stroke="{C_RED}" stroke-width="6" stroke-linecap="round"/>')
text(BX1 + 8, ROW_GND + 4, "GND排", 12, C_BLK, "bold")
text(BX1 + 8, ROW_VP + 4, "V+排", 12, C_RED, "bold")
text(BX1 + 8, ROW_SIG + 4, "信号排", 12, "#b97400", "bold")
for i, cx in enumerate(COLS):
    for ry, rc in ((ROW_GND, "#333"), (ROW_VP, "#7a1010"), (ROW_SIG, "#9a6200")):
        add(f'<circle cx="{cx}" cy="{ry}" r="6" fill="{C_PAD}" stroke="{rc}" '
            f'stroke-width="2.5"/>')
    ch, joint, dpin = CH_INFO[i]
    text(cx, 512, ch, 10.5, "#ffffff", "bold", "middle")
    text(cx, 526, joint, 10.5, "#c9f0da", "normal", "middle")
    text(cx + 11, 570, dpin, 9.5, "#ffdf8a", "bold")  # 贴在信号线旁

# ============================================================ 舵机示例 (×8)
text(868, 160, "DM-S0020 2.1g 舵机 ×8 (A1)", 13, C_TXT, "bold", "end")
text(868, 178, "JR 2.54mm: 棕GND·红V+·橙信号", 12, C_GRAY, "normal", "end")
text(868, 196, "每列插 1 个舵机,棕线朝上(GND排)", 12, C_GRAY, "normal", "end")
add('<rect x="884" y="140" width="96" height="88" rx="8" fill="#2b3a55" '
    'stroke="#1a2436" stroke-width="2.5"/>')
add('<rect x="872" y="172" width="12" height="18" rx="3" fill="#2b3a55"/>')
add('<rect x="980" y="172" width="12" height="18" rx="3" fill="#2b3a55"/>')
add('<circle cx="908" cy="140" r="13" fill="#3d5378"/>')
add('<circle cx="908" cy="140" r="5" fill="#e8e8e8"/>')
add('<rect x="904" y="108" width="8" height="34" rx="4" fill="#f0f0f0" '
    'stroke="#bbb" stroke-width="1.5"/>')
# 三色排线 → JR 插头 → 指向 CH2 列
for off, cc in ((0, "#7a4a21"), (5, C_RED), (10, C_SIG)):
    add(f'<path d="M {916 + off} 228 C {916 + off} 268, {891 + off // 2} 268, '
        f'{891 + off // 2} 296" fill="none" stroke="{cc}" stroke-width="3"/>')
add('<rect x="884" y="296" width="24" height="44" rx="4" fill="#161616"/>')
for hy in (306, 318, 330):
    add(f'<circle cx="896" cy="{hy}" r="3" fill="#555"/>')
wire([(896, 344), (896, ROW_GND - 16)], C_GRAY, 2, dash="4 5")
add(f'<path d="M 891 {ROW_GND - 18} L 901 {ROW_GND - 18} L 896 {ROW_GND - 9} Z" '
    f'fill="{C_GRAY}"/>')

# ============================================================ XIAO ESP32-S3
KX0, KY0, KX1, KY1 = 600, 680, 760, 940
add(f'<rect x="{KX0}" y="{KY0}" width="{KX1 - KX0}" height="{KY1 - KY0}" rx="16" '
    f'fill="{C_BOARD}" stroke="#0d0b0e" stroke-width="3"/>')
add(f'<rect x="{(KX0 + KX1) // 2 - 30}" y="{KY0 - 10}" width="60" height="32" rx="8" '
    f'fill="#b9bec6" stroke="#7e848d" stroke-width="2"/>')
text((KX0 + KX1) // 2, KY0 + 34, "Seeed XIAO", 10.5, "#e8e2ee", "bold", "middle")
text((KX0 + KX1) // 2, KY0 + 48, "ESP32-S3 (E1)", 10.5, "#e8e2ee", "bold", "middle")
add('<rect x="648" y="772" width="64" height="60" rx="6" fill="#3a333d" '
    'stroke="#57505b" stroke-width="2"/>')
text(680, 798, "ESP32", 12, "#cfc8d4", "bold", "middle")
text(680, 814, "-S3", 12, "#cfc8d4", "bold", "middle")

L_PADS = [  # (y, 名称, 副标, 已用)
    (740, "D0", "IO1", True), (770, "D1", "IO2", True),
    (800, "D2", "IO3", True), (830, "D3", "IO4", True),
    (860, "D4", "SDA", True), (890, "D5", "SCL", True),
    (920, "D6", "TX", False),
]
R_PADS = [
    (740, "5V", "", False), (770, "GND", "", True),
    (800, "3V3", "", True), (830, "D10", "IO9", True),
    (860, "D9", "IO8", True), (890, "D8", "IO7", True),
    (920, "D7", "IO44", True),
]
for y, name, sub, used in L_PADS:
    add(f'<circle cx="{KX0 + 5}" cy="{y}" r="7" fill="{C_PAD}" stroke="#8a6d1a" '
        f'stroke-width="2"/>')
    text(KX0 + 18, y - 1, name, 12, "#fff" if used else "#6f6875", "bold")
    if sub:
        text(KX0 + 18, y + 11, sub, 9, "#9a92a0")
for y, name, sub, used in R_PADS:
    add(f'<circle cx="{KX1 - 5}" cy="{y}" r="7" fill="{C_PAD}" stroke="#8a6d1a" '
        f'stroke-width="2"/>')
    text(KX1 - 18, y - 1, name, 12, "#fff" if used else "#6f6875", "bold", "end")
    if sub:
        text(KX1 - 18, y + 11, sub, 9, "#9a92a0", "normal", "end")
text(592, 924, "留空!", 11, C_RED, "bold", "end")

# ============================================================ 信号线 8 根 (无交叉车道)
# 左列 D0-D3 → CH0-3: riser 在 XIAO 左侧, 列越右车道越低
L_ROUTE = [  # (pad_y, riser_x, lane_y, col_x)
    (740, 580, 590, COLS[0]), (770, 570, 601, COLS[1]),
    (800, 560, 612, COLS[2]), (830, 550, 623, COLS[3]),
]
for py, rx, ly, cx in L_ROUTE:
    wire([(KX0 + 5, py), (rx, py), (rx, ly), (cx, ly), (cx, ROW_SIG + 6)], C_SIG)
# 右列 D10,D9,D8,D7 → CH4-7: riser 在 XIAO 右侧(950-986), 列越右车道越低
R_ROUTE = [
    (830, 950, 590, COLS[4]), (860, 962, 601, COLS[5]),
    (890, 974, 612, COLS[6]), (920, 986, 623, COLS[7]),
]
for py, rx, ly, cx in R_ROUTE:
    wire([(KX1 - 5, py), (rx, py), (rx, ly), (cx, ly), (cx, ROW_SIG + 6)], C_SIG)
text(596, 660, "髋 CH0–CH3", 12, "#b97400", "bold")
text(995, 660, "腿 CH4–CH7", 12, "#b97400", "bold")

# ============================================================ OLED (I²C)
OX0, OY0 = 1560, 700
text(OX0 - 60, 690, "ER-OLEDM0.49 · 64×32 · SSD1306 · I²C 0x3C (E2)", 13, C_TXT, "bold")
add(f'<rect x="{OX0}" y="{OY0}" width="240" height="150" rx="10" fill="#2559a7" '
    f'stroke="#173d78" stroke-width="3"/>')
add(f'<rect x="{OX0 + 30}" y="{OY0 + 22}" width="185" height="96" rx="4" fill="#05070d"/>')
text(OX0 + 122, OY0 + 82, "(,,>ω<,,)", 24, "#eaf2ff", "bold", "middle")
for mx, my in ((OX0 + 14, OY0 + 14), (OX0 + 226, OY0 + 14),
               (OX0 + 14, OY0 + 136), (OX0 + 226, OY0 + 136)):
    add(f'<circle cx="{mx}" cy="{my}" r="6" fill="#fff" stroke="#173d78" stroke-width="2"/>')
OLED_PADS = [(730, "GND", C_BLK), (760, "VCC", C_RED), (790, "SCL", C_SCL), (820, "SDA", C_SDA)]
for py, name, cc in OLED_PADS:
    add(f'<circle cx="{OX0 - 2}" cy="{py}" r="6.5" fill="{C_PAD}" stroke="#8a6d1a" '
        f'stroke-width="2"/>')
    text(OX0 + 12, py + 4, name, 11, "#fff", "bold")

# OLED 供电 GND/VCC: 出右侧焊盘, 一个大拱跨过 4 根信号 riser(942→994), 绕板下走
raw_wire(f"M {KX1 - 5} 770 L 942 770 A 27 15 0 0 1 994 770 L 1022 770 "
         f"L 1022 940 Q 1022 952 1034 952 L 1500 952 Q 1512 952 1512 940 "
         f"L 1512 742 Q 1512 730 1524 730 L {OX0 - 2} 730", C_BLK)
raw_wire(f"M {KX1 - 5} 800 L 942 800 A 27 15 0 0 1 994 800 L 1010 800 "
         f"L 1010 950 Q 1010 962 1022 962 L 1512 962 Q 1524 962 1524 950 "
         f"L 1524 772 Q 1524 760 1536 760 L {OX0 - 2} 760", C_RED)
text(1080, 946, "OLED: GND / VCC←3V3(非电池轨!)", 11, C_TXT, "bold")
# I²C: D4/SDA(蓝) D5/SCL(绿) 从左侧绕板底到 OLED
wire([(KX0 + 5, 860), (530, 860), (530, 986), (1548, 986), (1548, 820), (OX0 - 2, 820)], C_SDA)
wire([(KX0 + 5, 890), (540, 890), (540, 974), (1536, 974), (1536, 790), (OX0 - 2, 790)], C_SCL)
text(1080, 1004, "SDA=D4/IO5(蓝) · SCL=D5/IO6(绿)", 11, C_TXT, "bold")

# ============================================================ XIAO 背面 B+/B−
add('<rect x="615" y="995" width="200" height="57" rx="8" fill="none" '
    'stroke="#555" stroke-width="2" stroke-dasharray="6 5"/>')
wire([(715, 995), (715, KY1)], "#888", 2, dash="3 4")
add(f'<circle cx="695" cy="1015" r="7" fill="{C_PAD}" stroke="#8a6d1a" stroke-width="2"/>')
add(f'<circle cx="768" cy="1015" r="7" fill="{C_PAD}" stroke="#8a6d1a" stroke-width="2"/>')
text(695, 1002, "B+", 11, C_RED, "bold", "middle")
text(768, 1002, "B−", 11, C_BLK, "bold", "middle")
text(715, 1046, "XIAO 背面焊盘,翻面直焊(见右上照片)", 10.5, C_GRAY, "normal", "middle")

# ============================================================ 固件映射代码框
add('<rect x="1300" y="330" width="420" height="230" rx="10" fill="#1e1e28" '
    'stroke="#3c3c50" stroke-width="2"/>')
code = [
    ("// mini-firmware.ino → XIAO ESP32-S3 移植", "#8a8aa0"),
    ("#include <ESP32Servo.h>   // 替代 Servo.h", "#7ec9f5"),
    ("const int servoPins[8] =  // CH0..CH7", "#d8d8e8"),
    ("  {1, 2, 3, 4, 9, 8, 7, 44};  // GPIO", "#f5c94e"),
    ("  // = D0 D1 D2 D3 D10 D9 D8 D7", "#8a8aa0"),
    ("Wire.begin(); // SDA=IO5(D4) SCL=IO6(D5)", "#d8d8e8"),
    ("// D6/IO43(TX) 留空: boot日志会抖舵机", "#e06060"),
    ("// 8 舵机占满 LEDC 8 路 PWM", "#8a8aa0"),
]
for i, (line, cc) in enumerate(code):
    text(1320, 362 + i * 25, line, 14, cc, "normal", "start", MONO)

# ============================================================ 要点框
add('<rect x="60" y="620" width="435" height="300" rx="12" fill="#fdf6e9" '
    'stroke="#e8b93a" stroke-width="2.5"/>')
text(80, 652, "⚠ 要点", 17, "#9a6200", "bold")
notes = [
    "全机共地: 电池−·舵机棕线·XIAO B−·OLED GND",
    "1S 直供(3.0–4.2V) 无升压/降压;开关串电池正极",
    "OLED 由 XIAO 3V3 供电,不接电池轨;地址 0x3C",
    "D6(TX/IO43) 留空调试;D7(RX) 可接舵机(上电静默)",
    "充电: 开关拨 ON 再插 USB-C(板载 1S 充电)",
    "电池 ≥25C(预留无人机)多无 PCM → 固件 ADC 低压切断",
    "舵机插头 JR 线序: 棕=GND 红=V+ 橙=信号",
    "CH0-3=髋 CH4-7=腿;具体腿位装配后 subtrim 校准",
]
for i, n in enumerate(notes):
    text(80, 684 + i * 29, "· " + n, 13.5, "#4a3a10")

add("</svg>")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(svg))
print(f"OK {OUT} ({os.path.getsize(OUT) // 1024} KB)")
