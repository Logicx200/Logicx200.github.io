import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import scipy.sparse as sparse
import scipy.sparse.linalg as splinalg

# 参数设置
hbar = 1.0
m = 0.5

# 空间网格
x_min, x_max = -60, 60
Nx = 6000
x = np.linspace(x_min, x_max, Nx)
dx = x[1] - x[0]

# 时间参数
dt = 0.001
t_max = 15
time_steps = min(int(t_max / dt), 15000)

# 势垒参数
V0 = 6.0
a = 2.0
x0_barrier = 0.0

# 定义势能函数
def potential(x):
    V = np.zeros_like(x)
    V[(x >= x0_barrier - a/2) & (x <= x0_barrier + a/2)] = V0
    return V

# 初始波函数
def initial_wavefunction(x):
    sigma_x = 1.2
    x0 = -15.0
    k0 = 2.5
    
    norm = (1/(np.pi**0.25 * np.sqrt(sigma_x)))
    return norm * np.exp(-(x - x0)**2/(4*sigma_x**2)) * np.exp(1j*k0*x)

# 改进的开放边界条件
class FarOpenBoundary:
    def __init__(self, x, dx, dt, hbar=1.0, m=0.5, boundary_width=200, observation_margin=20):
        self.x = x
        self.dx = dx
        self.dt = dt
        self.hbar = hbar
        self.m = m
        self.boundary_width = boundary_width
        self.observation_margin = observation_margin
        
        # 观察区域
        self.observation_min = -25
        self.observation_max = 25
        
        # 设置边界区域，确保在观察区域外很远
        left_boundary_start = x_min
        left_boundary_end = self.observation_min - observation_margin
        right_boundary_start = self.observation_max + observation_margin
        right_boundary_end = x_max
        
        # 确保边界区域有效
        if left_boundary_end <= left_boundary_start:
            left_boundary_end = left_boundary_start + 10
        
        if right_boundary_start >= right_boundary_end:
            right_boundary_start = right_boundary_end - 10
        
        self.left_boundary = (x >= left_boundary_start) & (x <= left_boundary_end)
        self.right_boundary = (x >= right_boundary_start) & (x <= right_boundary_end)
        
        # 创建非常温和的吸收函数
        self.absorption = np.ones_like(x)
        
        # 左边界吸收（只在最边缘处）
        if np.any(self.left_boundary):
            x_left = x[self.left_boundary]
            distance_from_edge = x_left - left_boundary_start
            total_width = left_boundary_end - left_boundary_start
            normalized_dist = distance_from_edge / total_width
            
            # 只在边界的最外侧20%区域有轻微吸收
            absorption_mask = normalized_dist > 0.8
            absorption_strength = np.zeros_like(x_left)
            absorption_strength[absorption_mask] = 0.05 * ((normalized_dist[absorption_mask] - 0.8) / 0.2)**2
            
            self.absorption[self.left_boundary] = 1.0 - absorption_strength
        
        # 右边界吸收（只在最边缘处）
        if np.any(self.right_boundary):
            x_right = x[self.right_boundary]
            distance_from_edge = right_boundary_end - x_right
            total_width = right_boundary_end - right_boundary_start
            normalized_dist = distance_from_edge / total_width
            
            # 只在边界的最外侧20%区域有轻微吸收
            absorption_mask = normalized_dist > 0.8
            absorption_strength = np.zeros_like(x_right)
            absorption_strength[absorption_mask] = 0.05 * ((normalized_dist[absorption_mask] - 0.8) / 0.2)**2
            
            self.absorption[self.right_boundary] = 1.0 - absorption_strength
        
        print(f"Boundary settings:")
        print(f"  Observation region: {self.observation_min} to {self.observation_max}")
        print(f"  Left boundary: {left_boundary_start:.1f} to {left_boundary_end:.1f}")
        print(f"  Right boundary: {right_boundary_start:.1f} to {right_boundary_end:.1f}")
    
    def apply_boundary(self, psi):
        """Apply boundary conditions"""
        return psi * self.absorption

# 傅里叶谱方法
def fourier_method(psi, V, dt, dx, m=0.5, hbar=1.0):
    """Fourier spectral method"""
    N = len(psi)
    k = 2 * np.pi * np.fft.fftfreq(N, dx)
    
    # Split-operator method
    psi_k = np.fft.fft(psi)
    psi_k_half = psi_k * np.exp(-1j * hbar * k**2 * dt / (4 * m))
    psi_half = np.fft.ifft(psi_k_half)
    psi_potential = psi_half * np.exp(-1j * V * dt / hbar)
    psi_potential_k = np.fft.fft(psi_potential)
    psi_new_k = psi_potential_k * np.exp(-1j * hbar * k**2 * dt / (4 * m))
    psi_new = np.fft.ifft(psi_new_k)
    
    return psi_new

# 初始化
print("Initializing...")
print(f"Simulation time: {t_max} seconds")
print(f"Total space range: {x_min} to {x_max}")
print(f"Observation region: -25 to 25")

# 内存优化
max_array_size = 4000
save_interval = max(1, time_steps // max_array_size)

psi_time = np.zeros((min(time_steps, max_array_size), Nx), dtype=complex)
psi_time[0] = initial_wavefunction(x)
V = potential(x)

# 创建远离的边界处理器
boundary_handler = FarOpenBoundary(x, dx, dt, hbar, m, boundary_width=250, observation_margin=15)

# 记录参数
sigma_history = np.zeros(min(time_steps, max_array_size))
x_center_history = np.zeros(min(time_steps, max_array_size))
reflection_probs = np.zeros(min(time_steps, max_array_size))
transmission_probs = np.zeros(min(time_steps, max_array_size))
total_prob_history = np.zeros(min(time_steps, max_array_size))

# 新增：记录透射波和反射波的质心
transmission_center_history = np.zeros(min(time_steps, max_array_size))
reflection_center_history = np.zeros(min(time_steps, max_array_size))

print("Calculating wavefunction evolution...")
current_psi = psi_time[0].copy()
frame_count = 0

for i in range(1, time_steps):
    # 时间演化
    current_psi = fourier_method(current_psi, V, dt, dx, m, hbar)
    current_psi = boundary_handler.apply_boundary(current_psi)
    
    # 每隔save_interval步保存一次数据
    if i % save_interval == 0 and frame_count < max_array_size - 1:
        frame_count += 1
        psi_time[frame_count] = current_psi
        
        # 计算波包参数
        prob_density = np.abs(current_psi)**2
        total_prob = np.trapz(prob_density, dx=dx)
        total_prob_history[frame_count] = total_prob
        
        if total_prob > 1e-10:
            prob_density_normalized = prob_density / total_prob
            x_center = np.trapz(x * prob_density_normalized, dx=dx)
            sigma_current = np.sqrt(np.trapz((x - x_center)**2 * prob_density_normalized, dx=dx))
            
            x_center_history[frame_count] = x_center
            sigma_history[frame_count] = sigma_current
            
            # 计算透射和反射概率
            transmission_region = (x > x0_barrier + a/2) & (x <= boundary_handler.observation_max)
            reflection_region = (x < x0_barrier - a/2) & (x >= boundary_handler.observation_min)
            
            transmission_probs[frame_count] = np.trapz(prob_density[transmission_region], x[transmission_region])
            reflection_probs[frame_count] = np.trapz(prob_density[reflection_region], x[reflection_region])
            
            # 计算透射波和反射波的质心
            if transmission_probs[frame_count] > 0.01:  # 只有透射概率大于1%时才计算质心
                transmission_density = prob_density.copy()
                transmission_density[~transmission_region] = 0
                transmission_center = np.trapz(x * transmission_density, dx=dx) / transmission_probs[frame_count]
                transmission_center_history[frame_count] = transmission_center
            else:
                transmission_center_history[frame_count] = np.nan
                
            if reflection_probs[frame_count] > 0.01:  # 只有反射概率大于1%时才计算质心
                reflection_density = prob_density.copy()
                reflection_density[~reflection_region] = 0
                reflection_center = np.trapz(x * reflection_density, dx=dx) / reflection_probs[frame_count]
                reflection_center_history[frame_count] = reflection_center
            else:
                reflection_center_history[frame_count] = np.nan
    
    if i % 500 == 0:
        current_time = i * dt
        prob_density = np.abs(current_psi)**2
        total_prob = np.trapz(prob_density, dx=dx)
        prob_max_pos = x[np.argmax(prob_density)]
        
        print(f"Time t = {current_time:.2f}: Peak position: {prob_max_pos:.2f}, Total probability: {total_prob:.6f}")

# 调整数组大小
actual_frames = frame_count + 1
psi_time = psi_time[:actual_frames]
sigma_history = sigma_history[:actual_frames]
x_center_history = x_center_history[:actual_frames]
reflection_probs = reflection_probs[:actual_frames]
transmission_probs = transmission_probs[:actual_frames]
total_prob_history = total_prob_history[:actual_frames]
transmission_center_history = transmission_center_history[:actual_frames]
reflection_center_history = reflection_center_history[:actual_frames]

print(f"\nActual saved frames: {actual_frames}")

# 创建图形 - 只绘制一个图
fig, ax = plt.subplots(1, 1, figsize=(12, 8))

# 波函数演化（只显示观察区域）
observation_min, observation_max = -25, 25
ax.fill_between(x, V, 0, alpha=0.3, color='red', label=f'Potential Barrier (V0={V0})')
ax.axvline(x0_barrier - a/2, color='red', linestyle='--', alpha=0.5)
ax.axvline(x0_barrier + a/2, color='red', linestyle='--', alpha=0.5)

# 标记观察区域边界
ax.axvline(observation_min, color='gray', linestyle=':', alpha=0.7, linewidth=1, label='Observation Boundary')
ax.axvline(observation_max, color='gray', linestyle=':', alpha=0.7, linewidth=1)

# 初始波函数显示
prob_density_initial = np.abs(psi_time[0])**2
line_prob, = ax.plot(x, prob_density_initial, 'b-', linewidth=2, label='Probability Density |ψ|²')
line_real, = ax.plot(x, psi_time[0].real, 'g--', linewidth=1, alpha=0.6, label='Real Part Re(ψ)')
line_imag, = ax.plot(x, psi_time[0].imag, 'm--', linewidth=1, alpha=0.6, label='Imaginary Part Im(ψ)')

# 添加质心标记 - 初始只有一个质心
initial_center = x_center_history[0]
center_marker, = ax.plot([initial_center], [0], 'ro', markersize=8, label='Center of Mass')
center_line = ax.axvline(initial_center, color='r', linestyle='-', alpha=0.5, linewidth=2)

# 添加透射波和反射波的质心标记
transmission_center_marker, = ax.plot([], [], 'go', markersize=8, label='Transmission Center')
reflection_center_marker, = ax.plot([], [], 'bo', markersize=8, label='Reflection Center')
transmission_center_line = ax.axvline(np.nan, color='g', linestyle='-', alpha=0.5, linewidth=2)
reflection_center_line = ax.axvline(np.nan, color='b', linestyle='-', alpha=0.5, linewidth=2)

ax.set_xlim(observation_min, observation_max)
max_density_initial = np.max(prob_density_initial)
ax.set_ylim(-max_density_initial * 0.3, max_density_initial * 1.2)
ax.set_xlabel('Position x')
ax.set_ylabel('Amplitude')
ax.grid(True, alpha=0.3)
ax.set_title('Quantum Wave Packet Evolution (Observation Region: -25 to 25)', fontsize=14)
ax.legend(loc='upper right')

# 文本显示
time_text = ax.text(0.02, 0.95, '', transform=ax.transAxes, fontsize=11,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
prob_text = ax.text(0.02, 0.75, '', transform=ax.transAxes, fontsize=10,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7))
wavepacket_text = ax.text(0.02, 0.55, '', transform=ax.transAxes, fontsize=9,
                         bbox=dict(boxstyle="round,pad=0.3", facecolor="lightblue", alpha=0.7))

plt.tight_layout()

def update(frame):
    data_frame = min(frame, actual_frames - 1)
    current_psi = psi_time[data_frame]
    prob_density = np.abs(current_psi)**2
    
    # 动态调整y轴范围
    current_max_density = np.max(prob_density)
    if current_max_density > 0:
        y_max = max(current_max_density * 1.2, max_density_initial * 0.3)
        ax.set_ylim(-y_max * 0.3, y_max)
    
    line_prob.set_ydata(prob_density)
    line_real.set_ydata(current_psi.real)
    line_imag.set_ydata(current_psi.imag)
    
    # 更新总质心标记
    current_center = x_center_history[data_frame]
    center_marker.set_data([current_center], [0])
    center_line.set_xdata([current_center, current_center])
    
    # 更新透射波和反射波的质心标记
    transmission_center = transmission_center_history[data_frame]
    reflection_center = reflection_center_history[data_frame]
    
    if not np.isnan(transmission_center):
        transmission_center_marker.set_data([transmission_center], [0])
        transmission_center_line.set_xdata([transmission_center, transmission_center])
    else:
        transmission_center_marker.set_data([], [])
        transmission_center_line.set_xdata([np.nan, np.nan])
        
    if not np.isnan(reflection_center):
        reflection_center_marker.set_data([reflection_center], [0])
        reflection_center_line.set_xdata([reflection_center, reflection_center])
    else:
        reflection_center_marker.set_data([], [])
        reflection_center_line.set_xdata([np.nan, np.nan])
    
    current_time = data_frame * (t_max / (actual_frames - 1)) if actual_frames > 1 else 0
    time_text.set_text(f'Time t = {current_time:.2f} s')
    
    prob_text.set_text(f'Transmission: {transmission_probs[data_frame]:.3f}\nReflection: {reflection_probs[data_frame]:.3f}\nTotal Prob: {total_prob_history[data_frame]:.3f}')
    wavepacket_text.set_text(f'Wavepacket Width: {sigma_history[data_frame]:.3f}\nCenter Position: {x_center_history[data_frame]:.3f}')
    
    return (line_prob, line_real, line_imag, center_marker, center_line,
            transmission_center_marker, transmission_center_line,
            reflection_center_marker, reflection_center_line,
            time_text, prob_text, wavepacket_text)

print("Generating animation...")
ani = FuncAnimation(fig, update, frames=actual_frames, interval=30, blit=True)

plt.tight_layout()
plt.show()

# 打印最终结果
print(f"\n15-second Simulation Results:")
print(f"Initial total probability: {total_prob_history[0]:.6f}")
print(f"Final total probability: {total_prob_history[-1]:.6f}")
print(f"Probability decrease: {total_prob_history[0] - total_prob_history[-1]:.6f} (wavepacket left observation region)")
print(f"Final transmission probability: {transmission_probs[-1]:.4f}")
print(f"Final reflection probability: {reflection_probs[-1]:.4f}")
print(f"Wavepacket width change: {sigma_history[0]:.3f} → {sigma_history[-1]:.3f}")
print(f"Center of mass movement: {x_center_history[0]:.3f} → {x_center_history[-1]:.3f}")

# 打印透射波和反射波的最终位置
if not np.isnan(transmission_center_history[-1]):
    print(f"Final transmission center position: {transmission_center_history[-1]:.3f}")
if not np.isnan(reflection_center_history[-1]):
    print(f"Final reflection center position: {reflection_center_history[-1]:.3f}")

# 导出高质量GIF的代码 - 修复版
print("\nExporting high-quality GIF...")

# 设置导出参数
export_gif = True  # 设置为True以导出GIF
gif_filename = "quantum_wavepacket_evolution.gif"
gif_dpi = 100      # 降低DPI以减少内存使用[citation:9]
gif_fps = 30       # 降低帧率以确保完整导出[citation:4]

if export_gif:
    try:
        # 方法1：使用pillow写入器（推荐，质量较好）
        from matplotlib.animation import PillowWriter
        
        # 关键修复：明确指定帧数[citation:2][citation:4]
        export_frames = min(actual_frames, 1000)  # 进一步限制帧数以避免截断
        
        print(f"Exporting {export_frames} frames to {gif_filename}...")
        print("This may take a few minutes...")
        
        # 创建专门的导出进度条
        try:
            from tqdm import tqdm
            use_tqdm = True
        except ImportError:
            use_tqdm = False
            print("tqdm not available, using simple progress reporting")
        
        # 关键修复：在创建FuncAnimation时明确指定frames参数[citation:2][citation:4]
        # 创建新的动画对象用于导出 - 简化版本以减少内存使用[citation:9]
        fig_export, ax_export = plt.subplots(1, 1, figsize=(10, 6), dpi=gif_dpi)  # 减小图形尺寸
        
        # 设置与主图相同的内容（简化版本）
        ax_export.fill_between(x, V, 0, alpha=0.3, color='red', label=f'Potential Barrier (V0={V0})')
        ax_export.axvline(x0_barrier - a/2, color='red', linestyle='--', alpha=0.5)
        ax_export.axvline(x0_barrier + a/2, color='red', linestyle='--', alpha=0.5)
        ax_export.axvline(observation_min, color='gray', linestyle=':', alpha=0.7, linewidth=1)
        ax_export.axvline(observation_max, color='gray', linestyle=':', alpha=0.7, linewidth=1)
        
        # 初始波函数
        prob_density_initial = np.abs(psi_time[0])**2
        line_prob_export, = ax_export.plot(x, prob_density_initial, 'b-', linewidth=1.5)  # 减小线宽
        line_real_export, = ax_export.plot(x, psi_time[0].real, 'g--', linewidth=1, alpha=0.6)
        line_imag_export, = ax_export.plot(x, psi_time[0].imag, 'm--', linewidth=1, alpha=0.6)
        
        # 质心标记
        initial_center = x_center_history[0]
        center_marker_export, = ax_export.plot([initial_center], [0], 'ro', markersize=6)  # 减小标记大小
        center_line_export = ax_export.axvline(initial_center, color='r', linestyle='-', alpha=0.5, linewidth=1)
        
        ax_export.set_xlim(observation_min, observation_max)
        max_density_initial = np.max(prob_density_initial)
        ax_export.set_ylim(-max_density_initial * 0.3, max_density_initial * 1.2)
        ax_export.set_xlabel('Position x')
        ax_export.set_ylabel('Amplitude')
        ax_export.grid(True, alpha=0.3)
        ax_export.set_title('Quantum Wave Packet Evolution', fontsize=12)
        ax_export.legend(loc='upper right')
        
        # 文本显示
        time_text_export = ax_export.text(0.02, 0.95, '', transform=ax_export.transAxes, fontsize=9,
                                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
        prob_text_export = ax_export.text(0.02, 0.75, '', transform=ax_export.transAxes, fontsize=8,
                                        bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7))
        
        plt.tight_layout()
        
        # 关键修复：预计算所有帧的数据以减少内存使用[citation:9]
        def update_export(frame):
            # 均匀采样帧，确保覆盖整个时间范围
            data_frame = min(int(frame * (actual_frames - 1) / (export_frames - 1)), actual_frames - 1)
            
            current_psi = psi_time[data_frame]
            prob_density = np.abs(current_psi)**2
            
            # 动态调整y轴范围
            current_max_density = np.max(prob_density)
            if current_max_density > 0:
                y_max = max(current_max_density * 1.2, max_density_initial * 0.3)
                ax_export.set_ylim(-y_max * 0.3, y_max)
            
            line_prob_export.set_ydata(prob_density)
            line_real_export.set_ydata(current_psi.real)
            line_imag_export.set_ydata(current_psi.imag)
            
            # 更新质心标记
            current_center = x_center_history[data_frame]
            center_marker_export.set_data([current_center], [0])
            center_line_export.set_xdata([current_center, current_center])
            
            current_time = data_frame * (t_max / (actual_frames - 1)) if actual_frames > 1 else 0
            time_text_export.set_text(f'Time t = {current_time:.2f} s')
            
            prob_text_export.set_text(f'T: {transmission_probs[data_frame]:.3f}\nR: {reflection_probs[data_frame]:.3f}')
            
            return (line_prob_export, line_real_export, line_imag_export, 
                   center_marker_export, center_line_export,
                   time_text_export, prob_text_export)
        
        # 关键修复：创建动画时明确指定frames参数[citation:2][citation:4]
        print("Creating animation object...")
        ani_export = FuncAnimation(fig_export, update_export, frames=export_frames, 
                                 interval=1000/gif_fps, blit=True, repeat=False)
        
        # 设置写入器参数 - 降低质量以换取完整导出[citation:9]
        writer = PillowWriter(fps=gif_fps, 
                             bitrate=1000,  # 降低比特率
                             codec=None)
        
        # 保存GIF
        print("Saving GIF...")
        if use_tqdm:
            with tqdm(total=export_frames, desc="Exporting GIF") as pbar:
                def progress_callback(current_frame, total_frames):
                    pbar.n = current_frame + 1
                    pbar.refresh()
                
                ani_export.save(gif_filename, writer=writer, 
                              progress_callback=progress_callback,
                              dpi=gif_dpi)
        else:
            # 简单进度显示
            ani_export.save(gif_filename, writer=writer, dpi=gif_dpi)
            print(f"Saved {export_frames} frames")
        
        print(f"Successfully exported GIF: {gif_filename}")
        print(f"GIF specifications: {export_frames} frames, {gif_fps} fps, {gif_dpi} DPI")
        
        plt.close(fig_export)
        
    except ImportError:
        print("Pillow library not available. Using default writer...")
        # 备选方案：使用默认写入器
        # 关键修复：减少帧数[citation:4]
        simple_export_frames = min(actual_frames, 200)
        simple_ani = FuncAnimation(fig, update, frames=simple_export_frames, interval=1000/15, blit=True)
        simple_ani.save(gif_filename, writer='pillow', fps=15, dpi=80)
        print(f"GIF exported using default writer: {gif_filename}")
    
    except Exception as e:
        print(f"Error exporting GIF: {e}")
        print("Trying alternative method with ImageMagick...")
        
        # 备选方案：使用imagemagick（如果可用）[citation:10]
        try:
            # 关键修复：对于ImageMagick，也需要明确指定帧数[citation:2]
            simple_export_frames = min(actual_frames, 200)
            simple_ani = FuncAnimation(fig, update, frames=simple_export_frames, interval=1000/15, blit=True)
            simple_ani.save(gif_filename, writer='imagemagick', fps=15)
            print(f"GIF exported using imagemagick: {gif_filename}")
        except Exception as e2:
            print(f"ImageMagick also failed: {e2}")
            print("All export methods failed. Please install pillow: pip install pillow")
else:
    print("GIF export disabled. Set export_gif = True to enable.")