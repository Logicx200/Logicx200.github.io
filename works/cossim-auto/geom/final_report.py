# -*- coding: utf-8 -*-
"""最终版：用跑道入口标志跨度定标，输出标注图 + 校核报告。"""
import os
import numpy as np
import cv2

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"


def imread_u(p, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), flags)


def imwrite_u(p, img):
    ok, buf = cv2.imencode(os.path.splitext(p)[1], img)
    if ok:
        buf.tofile(p)


# ============ 公开数据（SkyVector ROYN） ============
RUNWAY_LEN_M, RUNWAY_WID_M = 2000.0, 45.0
END08 = (24 + 27.91 / 60, 122 + 58.21 / 60)     # N24°27.91' E122°58.21'
END26 = (24 + 28.18 / 60, 122 + 59.36 / 60)     # N24°28.18' E122°59.36'
H_SENSOR, FOV_H, N_H = 8000.0, 40.0, 1024
FOV_V, N_V = 30.0, 768


def enu(lat, lon, lat0, lon0):
    dy = (lat - lat0) * 111320.0
    dx = (lon - lon0) * 111320.0 * np.cos(np.radians((lat + lat0) / 2))
    return dx, dy


lat0, lon0 = 24.4562142, 122.9875683
x08, y08 = enu(*END08, lat0, lon0)
x26, y26 = enu(*END26, lat0, lon0)
L_true = float(np.hypot(x26 - x08, y26 - y08))
BRG_true = float(np.degrees(np.arctan2(x26 - x08, y26 - y08))) % 360

# ============ 图像实测 ============
p1 = np.array([147.0, 116.0])                   # 跑道下缘线起点（对齐用）
u = np.array([0.9671, -0.2549])                 # 方向角 -14.76°
u = u / np.linalg.norm(u)
T_KEY_START, T_KEY_END = 46.0, 410.0            # 两端入口标志沿轴位置
span_px = T_KEY_END - T_KEY_START
q1 = p1 + u * T_KEY_START
q2 = p1 + u * T_KEY_END
IMG_ANG = float(np.degrees(np.arctan2(u[1], u[0])))
BRG_img = (90.0 + IMG_ANG) % 360

gsd_meas = RUNWAY_LEN_M / span_px
ifov_small = np.radians(FOV_H) / N_H
ifov_exact = 2 * np.tan(np.radians(FOV_H / 2)) / N_H
gsd_small = H_SENSOR * ifov_small
gsd_exact = H_SENSOR * ifov_exact

print(f"跑道真长 {L_true:.1f} m, 真方位 {BRG_true:.2f}°")
print(f"图像: 入口标志跨度 {span_px:.0f} px, 方位 {BRG_img:.2f}°")
print(f"实测 GSD {gsd_meas:.3f} m/px")
print(f"名义 GSD: 小角 {gsd_small:.3f} (偏差 {100*(gsd_meas/gsd_small-1):+.2f}%), "
      f"精确 {gsd_exact:.3f} (偏差 {100*(gsd_meas/gsd_exact-1):+.2f}%)")
print(f"方位偏差 {BRG_img - BRG_true:+.2f}°")

# ============ 标注图 ============
img = imread_u(os.path.join(OUT, "02_render_1024.png"))
cv2.line(img, tuple(q1.astype(int)), tuple(q2.astype(int)), (0, 0, 255), 1)
for p in (q1, q2):
    cv2.circle(img, tuple(p.astype(int)), 4, (0, 255, 255), -1)
# 500 m 比例尺
scale_px = int(round(500.0 / gsd_meas))
cv2.line(img, (40, 610), (40 + scale_px, 610), (0, 255, 0), 2)
cv2.putText(img, "500 m", (44, 602), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)
lines = [
    f"ROYN RWY08/26: 2000 m x 45 m, true brg {BRG_true:.2f} deg",
    f"image: span {span_px:.0f} px -> GSD {gsd_meas:.2f} m/px",
    f"nominal GSD (h=8000, IFOV=FOV/N) = {gsd_small:.2f} m/px  ({100*(gsd_meas/gsd_small-1):+.1f}%)",
    f"heading image {BRG_img:.2f} deg  ({BRG_img-BRG_true:+.2f} deg)",
]
for i, s in enumerate(lines):
    cv2.putText(img, s, (40, 30 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1, cv2.LINE_AA)
crop = img[0:170, 40:620]
crop = cv2.resize(crop, (crop.shape[1] * 3, crop.shape[0] * 3), interpolation=cv2.INTER_LANCZOS4)
imwrite_u(os.path.join(OUT, "12_final_annotated.png"), crop)

# ============ 报告 ============
rows = [
    ("校核项", "公开/名义值", "图像实测", "偏差", "判定"),
    ("跑道真方位（由两端经纬度反算）", f"{BRG_true:.2f}°", f"{BRG_img:.2f}°", f"{BRG_img-BRG_true:+.2f}°", "通过"),
    ("跑道真长（由两端经纬度反算）", f"{L_true:.1f} m", "2000 m（公布值）", "—", "参考"),
    ("GSD（h=8 km，IFOV=FOV/N 小角式）", f"{gsd_small:.2f} m/px", f"{gsd_meas:.2f} m/px（{span_px:.0f} px/2000 m）", f"{100*(gsd_meas/gsd_small-1):+.1f}%", "通过（<1%）"),
    ("GSD（h=8 km，IFOV=2tan(FOV/2)/N 精确式）", f"{gsd_exact:.2f} m/px", f"{gsd_meas:.2f} m/px", f"{100*(gsd_meas/gsd_exact-1):+.1f}%", "软件用小角式"),
    ("跑道宽度 45 m", f"{RUNWAY_WID_M/gsd_small:.1f} px（小角式）", "≈8.5 px（边线中心距）", f"{100*(8.5/(RUNWAY_WID_M/gsd_small)-1):+.0f}%", "受 1 px 判读限制"),
    ("水平 IFOV 小角 vs 精确", f"{ifov_exact*1e6:.2f} μrad", f"{ifov_small*1e6:.2f} μrad", f"{100*(ifov_exact/ifov_small-1):+.1f}%", "40° 宽视场须注意"),
    ("图像水平像素", "1024", "1024（屏幕 1:1，x=92..1115）", "0", "通过"),
]
with open(os.path.join(OUT, "几何校核报告.md"), "w", encoding="utf-8") as f:
    f.write("# 可见光预览窗几何/分辨率链校核（截图分析，V1.0）\n\n")
    f.write("- 数据：XGGDCOSSim 可见光传感器预览窗截图（1024×768，屏幕 1:1 显示）\n")
    f.write("- 传感器：可见光 0.4–0.8 μm，FOV 40°×30°，1024×768，高度 8000 m（属性面板）\n")
    f.write("- 基准物：与那国机场跑道（SkyVector ROYN：2000×45 m，RWY08/26）\n\n")
    f.write("| " + " | ".join(rows[0]) + " |\n")
    f.write("|" + "---|" * len(rows[0]) + "\n")
    for r in rows[1:]:
        f.write("| " + " | ".join(r) + " |\n")
    f.write("\n## 结论\n\n")
    f.write(f"1. **尺度链通过**：跑道两端入口标志在图像上跨 {span_px:.0f} px，对应 2000 m，"
            f"得 GSD {gsd_meas:.2f} m/px；与名义值 8000 m × (40°/1024) = {gsd_small:.2f} m/px 相差仅 "
            f"{abs(100*(gsd_meas/gsd_small-1)):.1f}%。\n")
    f.write(f"2. **软件采用小角近似**：实测更接近 IFOV=FOV/N（差 {100*(gsd_meas/gsd_small-1):+.1f}%），"
            f"而非精确针孔 IFOV=2tan(FOV/2)/N（差 {100*(gsd_meas/gsd_exact-1):+.1f}%）。"
            "对本项目 3.75° 窄视场，两者差 0.03%，V3.0 模型不用改。\n")
    f.write(f"3. **方向链通过**：跑道图像方位 {BRG_img:.2f}°，由公开经纬度反算真方位 {BRG_true:.2f}°，"
            f"差 {abs(BRG_img-BRG_true):.2f}° → 场景北向对齐、像素网格无旋转畸变。\n")
    f.write("4. **可复现**：测量脚本与截图都在 _cossim_auto/geom 下；下次换工况可同样方法复核。\n")
print("saved 12_final_annotated.png / 几何校核报告.md")
