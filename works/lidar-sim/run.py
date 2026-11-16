"""
run.py —— 搭一个示例场景，仿真一帧点云，并输出可视化图片 + CSV。

用法：
    python run.py

输出（写到 outputs/）：
    pointcloud.csv        点云 (x, y, z, intensity, is_mixed)
    fig_3d.png            三维点云，按距离着色，混合像素标红
    fig_birdseye.png      俯视图（x-z），按强度着色
    fig_range_image.png   距离图 + 强度图（像相机一样看雷达）
"""

import os
import numpy as np

import lidar_sim as ls

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
os.makedirs(OUT, exist_ok=True)


def build_scene():
    """一个简单的街景：地面 + 背景墙 + 车 + 卡车 + 行人 + 一个黑色低反目标。

    背景墙的作用很关键：它让每个物体边缘的「远侧」子射线都命中一个量程内的
    表面，从而稳定触发混合像素（否则远侧会命中超量程空地、被判为无回波）。
    """
    return [
        ls.GroundPlane(y=0.0, reflectance=0.30),
        # 背景墙（在量程 40m 内，贯穿整个视场）
        ls.AABB([-18.0, 0.0, 28.0], [18.0, 10.0, 30.0], reflectance=0.55),
        # 左侧黑色箱子（低反射率 → 演示丢点/空洞）
        ls.AABB([-6.0, 0.0, 11.0], [-3.0, 1.0, 13.0], reflectance=0.05),
        # 小汽车
        ls.AABB([-2.0, 0.0, 12.0], [2.0, 1.5, 16.0], reflectance=0.45),
        # 行人（细高，演示边缘混合像素）
        ls.AABB([2.2, 0.0, 9.0], [2.7, 1.8, 9.5], reflectance=0.50),
        # 卡车
        ls.AABB([4.0, 0.0, 10.0], [8.0, 3.0, 15.0], reflectance=0.40),
    ]


def main():
    sensor = ls.LidarSensor(origin=(0.0, 2.0, 0.0),
                            yaw_fov=(-35.0, 35.0),
                            pitch_fov=(-25.0, 5.0),
                            H=240, V=120,
                            beam_div=6e-3,
                            max_range=40.0,
                            range_noise=(0.01, 0.002),
                            speckle=0.35)

    scene = build_scene()
    frame = ls.simulate_frame(sensor, scene, seed=1, beam_sub=5, mixed_threshold=0.5)

    pts = frame['points']
    I = frame['intensity']
    mixed = frame['is_mixed']

    # ---- 保存 CSV ----
    header = 'x,y,z,intensity,is_mixed'
    data = np.column_stack([pts, I, mixed.astype(int)])
    np.savetxt(os.path.join(OUT, 'pointcloud.csv'), data,
               delimiter=',', header=header, comments='', fmt='%.4f')

    # ---- 打印统计 ----
    s = frame['stats']
    print('===== 单帧点云仿真结果 =====')
    for k, v in s.items():
        print(f'  {k:12s}: {v}')
    print(f'  点云已保存: outputs/pointcloud.csv  ({len(pts)} 个点)')

    _plot(sensor, frame)


def _plot(sensor, frame):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    # 中文字体（Windows 上的微软雅黑），避免图里中文变方框
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    pts = frame['points']
    I = frame['intensity']
    mixed = frame['is_mixed']
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    R = frame['range']

    # ================= 图 1：三维点云 =================
    fig = plt.figure(figsize=(11, 5))
    ax = fig.add_subplot(121, projection='3d')
    ax.scatter(x[~mixed], y[~mixed], z[~mixed], c=R[~mixed],
               cmap='turbo', s=2, linewidths=0, label='普通点')
    if mixed.any():
        ax.scatter(x[mixed], y[mixed], z[mixed], c='red', s=9,
                   linewidths=0, label='混合像素', depthshade=False)
    ax.set_xlabel('x (m)'); ax.set_ylabel('y (m)'); ax.set_zlabel('z (m)')
    ax.set_title('一帧点云（按距离着色，红=混合像素）')
    ax.set_box_aspect((np.ptp(x), np.ptp(y), np.ptp(z)))
    ax.legend(loc='upper left', fontsize=8)

    # ================= 图 2：俯视图 =================
    ax2 = fig.add_subplot(122)
    sc = ax2.scatter(x[~mixed], z[~mixed], c=I[~mixed], cmap='inferno',
                     s=3, linewidths=0, norm=Normalize(0, 1.5), label='普通点')
    if mixed.any():
        ax2.scatter(x[mixed], z[mixed], c='cyan', s=18, linewidths=0,
                    label='混合像素', marker='x')
    ax2.plot([0], [0], 'k^', ms=8, label='传感器')
    ax2.set_xlabel('x (m)'); ax2.set_ylabel('z (m)')
    ax2.set_title('俯视图（x-z，按强度着色，青×=混合像素）')
    ax2.axis('equal'); ax2.legend(loc='upper right', fontsize=8)
    cb = fig.colorbar(sc, ax=ax2, fraction=0.046, pad=0.04)
    cb.set_label('强度（任意单位）')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'fig_3d.png'), dpi=130)
    plt.close(fig)

    # ================= 图 3：距离图 + 强度图 =================
    fig2, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    im0 = axes[0].imshow(frame['range_image'], cmap='turbo', aspect='auto')
    axes[0].set_title('距离图（每个像素 = 该方向的距离）')
    axes[0].set_xlabel('水平采样'); axes[0].set_ylabel('垂直采样')
    fig2.colorbar(im0, ax=axes[0], fraction=0.046, pad=0.04, label='距离 (m)')

    im1 = axes[1].imshow(frame['intensity_image'], cmap='inferno',
                         aspect='auto', norm=Normalize(0, 1.5))
    axes[1].set_title('强度图（低反目标成黑洞 → 丢点）')
    axes[1].set_xlabel('水平采样'); axes[1].set_ylabel('垂直采样')
    fig2.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04, label='强度')
    fig2.tight_layout()
    fig2.savefig(os.path.join(OUT, 'fig_range_image.png'), dpi=130)
    plt.close(fig2)

    print('  已输出: outputs/fig_3d.png, fig_birdseye.png(并入fig_3d), fig_range_image.png')


if __name__ == '__main__':
    main()
