%% 避雷针电场与电势分布模拟 - 自动递增文件夹版本
% 作者：基于拉普拉斯方程的三维有限差分求解
% 日期：2025-12-29
% 功能：模拟圆锥-圆柱组合避雷针的电场分布，每次运行创建独立文件夹

clear all; close all; clc;
warning('off', 'MATLAB:legend:PlotEmpty');
format short g;

%% 0. 参数设置（提前定义，用于创建目录）
fprintf('=== 避雷针电场模拟程序 ===\n');

% 几何参数
theta_deg = 29;              % 圆锥顶角（度）
theta = deg2rad(theta_deg);  % 转换为弧度
R_base = 0.015;              % 底面半径 1.5cm -> 0.015m
H_cone = R_base / tan(theta/2); % 圆锥高度（根据几何关系计算）
H_cylinder = 1.0;            % 圆柱高度 1m
H_total = H_cone + H_cylinder; % 避雷针总高度

% 仿真区域参数
Lx = 1.0;          % x方向长度 1m
Ly = 1.0;          % y方向长度 1m
Lz = 3.0;          % z方向高度 3m

% 网格参数
Nx = 60;           % x方向点数
Ny = 60;           % y方向点数
Nz = 80;           % z方向点数

% 边界条件（上表面为-1e6V）
V_top = -1e6;      % 上底面电势 -10^6 V
V_bottom = 0;      % 下底面（地面）电势 0 V
V_conductor = 0;   % 避雷针电势（接地）

% 求解参数
max_iter = 8000;   % 最大迭代次数
tolerance = 1e-5;  % 收敛容差
omega = 1.6;       % 超松弛因子

fprintf('参数设置完成：\n');
fprintf('  圆锥顶角：%.1f度，底面半径：%.3fm\n', theta_deg, R_base);
fprintf('  圆锥高度：%.3fm，圆柱高度：%.3fm\n', H_cone, H_cylinder);
fprintf('  仿真区域：%.1fx%.1fx%.1f m³\n', Lx, Ly, Lz);
fprintf('  边界条件：上底面 %.1e V，地面 0 V，避雷针 0 V\n', V_top);

%% 1. 创建自动递增的输出目录
fprintf('\n=== 创建输出目录 ===\n');

% 基本输出目录名称
base_dir_name = 'LightningRod_Simulation';

% 查找已存在的目录
existing_dirs = dir([base_dir_name '*']);
dir_numbers = [];

if ~isempty(existing_dirs)
    for i = 1:length(existing_dirs)
        if existing_dirs(i).isdir
            dir_name = existing_dirs(i).name;
            % 提取目录名中的数字
            num_str = regexp(dir_name, ['(?<=' base_dir_name '_)\d+'], 'match');
            if ~isempty(num_str)
                dir_numbers = [dir_numbers, str2double(num_str{1})];
            end
        end
    end
end

% 确定新的目录编号
if isempty(dir_numbers)
    new_dir_number = 1;
else
    new_dir_number = max(dir_numbers) + 1;
end

% 创建新的输出目录
output_dir = sprintf('%s_%03d_theta%d', base_dir_name, new_dir_number, theta_deg);
if ~exist(output_dir, 'dir')
    mkdir(output_dir);
end

% 在输出目录内创建子目录用于分类存储
sub_dirs = {'figures', 'data', 'reports', 'plots'};
for i = 1:length(sub_dirs)
    sub_dir_path = fullfile(output_dir, sub_dirs{i});
    if ~exist(sub_dir_path, 'dir')
        mkdir(sub_dir_path);
    end
end

fprintf('  输出目录: %s\n', output_dir);
fprintf('  子目录: figures/, data/, reports/, plots/\n');

%% 2. 创建均匀网格
fprintf('\n=== 创建计算网格 ===\n');

% 创建均匀网格
x = linspace(-Lx/2, Lx/2, Nx);
y = linspace(-Ly/2, Ly/2, Ny);
z = linspace(0, Lz, Nz);

% 计算网格间距
dx = x(2) - x(1);
dy = y(2) - y(1);
dz = z(2) - z(1);

fprintf('  网格尺寸：%dx%dx%d (总共%d个节点)\n', Nx, Ny, Nz, Nx*Ny*Nz);
fprintf('  网格间距：dx=%.3e m, dy=%.3e m, dz=%.3e m\n', dx, dy, dz);

% 创建三维网格
[X, Y, Z] = meshgrid(x, y, z);

%% 3. 定义避雷针几何形状
fprintf('\n=== 定义避雷针几何 ===\n');

% 初始化几何标记矩阵
is_conductor = zeros(Ny, Nx, Nz);  % 避雷针内部标记
is_fixed = zeros(Ny, Nx, Nz);      % 固定电势点标记
V = zeros(Ny, Nx, Nz);             % 电势矩阵

% 计算每个网格点到原点的水平距离
R = sqrt(X.^2 + Y.^2);

% 标记圆柱部分 (z <= H_cylinder)
cylinder_height_mask = Z <= H_cylinder;
cylinder_radius_mask = R <= R_base;
is_conductor(cylinder_height_mask & cylinder_radius_mask) = 1;

% 标记圆锥部分 (H_cylinder < z <= H_total)
for k = 1:Nz
    z_val = z(k);
    if z_val > H_cylinder && z_val <= H_total
        % 圆锥半径随高度线性减小
        r_cone = R_base * (H_total - z_val) / H_cone;
        cone_mask = (Z(:, :, k) <= z_val) & (R(:, :, k) <= r_cone);
        is_conductor(:, :, k) = is_conductor(:, :, k) | cone_mask;
    end
end

% 设置边界条件
% 1. 下底面 (z=0, 地面) - 固定为0V
V(:, :, 1) = V_bottom;
is_fixed(:, :, 1) = 1;

% 2. 上底面 (z=Lz) - 固定为-1e6V
V(:, :, end) = V_top;
is_fixed(:, :, end) = 1;

% 3. 避雷针表面和内部 - 固定为0V
V(is_conductor == 1) = V_conductor;
is_fixed(is_conductor == 1) = 1;

% 统计信息
num_conductor = sum(is_conductor(:));
num_fixed = sum(is_fixed(:));
num_total = Nx * Ny * Nz;

fprintf('  几何定义完成：\n');
fprintf('    导体节点数：%d (占%.2f%%)\n', num_conductor, 100*num_conductor/num_total);
fprintf('    固定边界点：%d (占%.2f%%)\n', num_fixed, 100*num_fixed/num_total);

%% 4. 初始化电势分布
fprintf('\n=== 初始化电势分布 ===\n');

% 设置初始猜测 - 线性分布从地面到顶部
for k = 1:Nz
    z_val = z(k);
    % 线性插值
    V_initial = V_bottom + (V_top - V_bottom) * (z_val / Lz);
    
    % 只设置非固定点的初始值
    non_fixed_mask = (is_fixed(:, :, k) == 0);
    V(:, :, k) = V(:, :, k) + V_initial .* non_fixed_mask;
end

% 显示初始电势范围
initial_min = min(V(:));
initial_max = max(V(:));
fprintf('  初始电势范围：%.2e 到 %.2e V\n', initial_min, initial_max);

%% 5. 求解拉普拉斯方程（有限差分法）
fprintf('\n=== 求解拉普拉斯方程 ===\n');

% 预计算系数
coeff_x = 1/(dx^2);
coeff_y = 1/(dy^2);
coeff_z = 1/(dz^2);
denom = 2*(coeff_x + coeff_y + coeff_z);

% 初始化收敛记录
residual_history = zeros(max_iter, 1);
iteration_time = zeros(max_iter, 1);

% 主迭代循环
fprintf('  开始迭代求解...\n');
start_time = tic;

for iter = 1:max_iter
    iter_start = tic;
    max_residual = 0;
    
    % 逐点更新 - 使用Checkerboard顺序（红黑排序）
    for color = 1:2
        for k = 2:Nz-1
            for j = 2:Ny-1
                % 确定起始列以实现Checkerboard模式
                start_i = 2 + mod(j+k+color, 2);
                for i = start_i:2:Nx-1
                    % 跳过固定点
                    if is_fixed(j, i, k) == 1
                        continue;
                    end
                    
                    % 拉普拉斯方程离散化（均匀网格简化）
                    V_new = (coeff_x*(V(j, i-1, k) + V(j, i+1, k)) + ...
                             coeff_y*(V(j-1, i, k) + V(j+1, i, k)) + ...
                             coeff_z*(V(j, i, k-1) + V(j, i, k+1))) / denom;
                    
                    % 计算残差
                    residual = abs(V_new - V(j, i, k));
                    max_residual = max(max_residual, residual);
                    
                    % 超松弛更新
                    V(j, i, k) = V(j, i, k) + omega * (V_new - V(j, i, k));
                end
            end
        end
    end
    
    % 记录收敛信息
    residual_history(iter) = max_residual;
    iteration_time(iter) = toc(iter_start);
    
    % 显示进度
    if mod(iter, 500) == 0
        fprintf('    迭代 %4d: 残差 = %.3e\n', iter, max_residual);
    end
    
    % 检查收敛
    if max_residual < tolerance && iter > 100
        fprintf('  收敛于迭代 %d，残差 = %.3e\n', iter, max_residual);
        residual_history = residual_history(1:iter);
        iteration_time = iteration_time(1:iter);
        break;
    end
    
    % 防止发散
    if max_residual > 1e10 || isnan(max_residual)
        fprintf('  发散于迭代 %d，残差 = %.3e\n', iter, max_residual);
        break;
    end
end

if iter == max_iter
    fprintf('  达到最大迭代次数 %d，最终残差 = %.3e\n', max_iter, max_residual);
    residual_history = residual_history(1:iter);
    iteration_time = iteration_time(1:iter);
end

total_time = toc(start_time);
fprintf('  求解完成，总时间：%.2f 秒\n', total_time);

%% 6. 计算电场强度
fprintf('\n=== 计算电场强度 ===\n');

% 使用中心差分计算电场 E = -∇V
Ex = zeros(Ny, Nx, Nz);
Ey = zeros(Ny, Nx, Nz);
Ez = zeros(Ny, Nx, Nz);

% 计算内部点的电场（中心差分）
for k = 2:Nz-1
    for j = 2:Ny-1
        for i = 2:Nx-1
            Ex(j, i, k) = -(V(j, i+1, k) - V(j, i-1, k)) / (2*dx);
            Ey(j, i, k) = -(V(j+1, i, k) - V(j-1, i, k)) / (2*dy);
            Ez(j, i, k) = -(V(j, i, k+1) - V(j, i, k-1)) / (2*dz);
        end
    end
end

% 边界点使用单侧差分
% x边界
for k = 2:Nz-1
    for j = 2:Ny-1
        % i=1 (左边界)
        Ex(j, 1, k) = -(V(j, 2, k) - V(j, 1, k)) / dx;
        % i=Nx (右边界)
        Ex(j, Nx, k) = -(V(j, Nx, k) - V(j, Nx-1, k)) / dx;
    end
end

% y边界
for k = 2:Nz-1
    for i = 2:Nx-1
        % j=1 (前边界)
        Ey(1, i, k) = -(V(2, i, k) - V(1, i, k)) / dy;
        % j=Ny (后边界)
        Ey(Ny, i, k) = -(V(Ny, i, k) - V(Ny-1, i, k)) / dy;
    end
end

% z边界
for j = 2:Ny-1
    for i = 2:Nx-1
        % k=1 (下边界)
        Ez(j, i, 1) = -(V(j, i, 2) - V(j, i, 1)) / dz;
        % k=Nz (上边界)
        Ez(j, i, Nz) = -(V(j, i, Nz) - V(j, i, Nz-1)) / dz;
    end
end

% 计算电场幅值
E_mag = sqrt(Ex.^2 + Ey.^2 + Ez.^2);

% 找到最大电场及其位置（排除导体内部）
E_mag_no_conductor = E_mag;
E_mag_no_conductor(is_conductor == 1) = 0;  % 将导体内部设为零

[max_E, max_idx] = max(E_mag_no_conductor(:));
[max_j, max_i, max_k] = ind2sub(size(E_mag), max_idx);
max_E_x = X(max_j, max_i, max_k);
max_E_y = Y(max_j, max_i, max_k);
max_E_z = Z(max_j, max_i, max_k);

% 找到最大电势和最小电势
[max_V, max_V_idx] = max(V(:));
[min_V, min_V_idx] = min(V(:));

fprintf('  电场计算完成：\n');
fprintf('    最大电场：%.3e V/m\n', max_E);
fprintf('    位置：(%.3f, %.3f, %.3f) m\n', max_E_x, max_E_y, max_E_z);
fprintf('    最大电势：%.3e V\n', max_V);
fprintf('    最小电势：%.3e V\n', min_V);

% 计算避雷针尖端的电场
[~, tip_z_idx] = min(abs(z - H_total));
[~, center_x_idx] = min(abs(x));
[~, center_y_idx] = min(abs(y));

if tip_z_idx <= Nz
    E_tip = E_mag(center_y_idx, center_x_idx, tip_z_idx);
    V_tip = V(center_y_idx, center_x_idx, tip_z_idx);
    fprintf('    避雷针尖端：\n');
    fprintf('      高度：%.3f m\n', z(tip_z_idx));
    fprintf('      电势：%.3e V\n', V_tip);
    fprintf('      电场：%.3e V/m\n', E_tip);
end

%% 7. 数据可视化
fprintf('\n=== 生成可视化结果 ===\n');

% 设置科研绘图样式
set(0, 'DefaultAxesFontSize', 12);
set(0, 'DefaultTextFontSize', 12);
set(0, 'DefaultLineLineWidth', 1.5);

% 保存所有图形句柄，用于后续导出
fig_handles = [];

% 7.1 收敛性分析图
fig1 = figure('Position', [100, 100, 800, 600], 'Name', '收敛性分析');
fig_handles = [fig_handles, fig1];

subplot(2, 2, 1);
semilogy(residual_history, 'b-', 'LineWidth', 2);
xlabel('迭代次数');
ylabel('最大残差 (V)');
title('收敛历史 (对数坐标)');
grid on; grid minor;

subplot(2, 2, 2);
plot(cumsum(iteration_time), residual_history, 'r-', 'LineWidth', 2);
set(gca, 'YScale', 'log');
xlabel('累计时间 (秒)');
ylabel('残差 (V)');
title('收敛速度');
grid on; grid minor;

subplot(2, 2, 3);
histogram(residual_history, 30, 'FaceColor', [0.2, 0.6, 0.8]);
xlabel('残差 (V)');
ylabel('频数');
title('残差分布');
grid on;

subplot(2, 2, 4);
if length(residual_history) > 10
    convergence_rate = zeros(size(residual_history));
    for i = 11:length(residual_history)
        convergence_rate(i) = residual_history(i) / residual_history(i-10);
    end
    plot(convergence_rate, 'g-', 'LineWidth', 2);
    xlabel('迭代次数');
    ylabel('收敛率');
    title('收敛率变化 (每10步)');
    ylim([0, 1]);
end
grid on; grid minor;

sgtitle(sprintf('数值求解收敛性分析 (θ = %.0f°)', theta_deg), 'FontSize', 14, 'FontWeight', 'bold');

% 7.2 三维电势分布 - 等势面图
fig2 = figure('Position', [100, 100, 1200, 500], 'Name', '三维电势分布');
fig_handles = [fig_handles, fig2];

% 子图1：三维等势面
subplot(1, 2, 1);
hold on;

% 计算几个代表性的等势面值
V_range = max_V - min_V;
isovalues = min_V + V_range * [0.2, 0.4, 0.6, 0.8]; % 选择4个等势面

% 获取颜色映射
num_isos = length(isovalues);
cmap = jet(num_isos);

for i = 1:num_isos
    isoval = isovalues(i);
    
    % 提取等势面
    fv = isosurface(X, Y, Z, V, isoval);
    
    if ~isempty(fv.vertices)
        p = patch(fv);
        % 使用正确的颜色 - 从颜色映射中获取
        set(p, 'FaceColor', cmap(i, :), 'EdgeColor', 'none', ...
               'FaceAlpha', 0.5, 'FaceLighting', 'gouraud');
    end
end

% 绘制避雷针
% 圆柱部分
[x_cyl, y_cyl, z_cyl] = cylinder(R_base, 30);
z_cyl = z_cyl * H_cylinder;
h_cyl = surf(x_cyl, y_cyl, z_cyl, 'FaceColor', [0.3, 0.3, 0.3], ...
             'EdgeColor', 'none', 'FaceAlpha', 0.8);

% 圆锥部分
[x_cone, y_cone, z_cone] = cylinder([R_base, 0.001], 30);
z_cone = z_cone * H_cone + H_cylinder;
h_cone = surf(x_cone, y_cone, z_cone, 'FaceColor', [0.5, 0.5, 0.5], ...
              'EdgeColor', 'none', 'FaceAlpha', 0.8);

% 设置图形属性
xlabel('x (m)'); ylabel('y (m)'); zlabel('z (m)');
title(sprintf('三维等势面分布 (\\theta = %.0f°)', theta_deg));
axis equal; grid on; view(45, 30);
light('Position', [1, 1, 2], 'Style', 'infinite');
lighting gouraud;
camlight('headlight');
colorbar;
caxis([min_V, max_V]);
legend([h_cyl, h_cone], {'避雷针圆柱', '避雷针圆锥'}, 'Location', 'best');

% 子图2：三维电势切片图
subplot(1, 2, 2);
hold on;

% 创建三个正交切片
slice_positions = {0, 0, H_total/2}; % x=0, y=0, z=H_total/2

% 绘制切片
h_slices = slice(X, Y, Z, V, slice_positions{1}, slice_positions{2}, slice_positions{3});
set(h_slices, 'EdgeColor', 'none', 'FaceAlpha', 0.8);

% 添加避雷针轮廓
[x_cyl, y_cyl, z_cyl] = cylinder(R_base, 30);
z_cyl = z_cyl * H_cylinder;
surf(x_cyl, y_cyl, z_cyl, 'FaceColor', [0.3, 0.3, 0.3], ...
     'EdgeColor', 'none', 'FaceAlpha', 0.5);

[x_cone, y_cone, z_cone] = cylinder([R_base, 0.001], 30);
z_cone = z_cone * H_cone + H_cylinder;
surf(x_cone, y_cone, z_cone, 'FaceColor', [0.5, 0.5, 0.5], ...
     'EdgeColor', 'none', 'FaceAlpha', 0.5);

% 标记切片位置
plot3([0, 0], [-Lx/2, Lx/2], [slice_positions{3}, slice_positions{3}], ...
      'r-', 'LineWidth', 2);
plot3([-Lx/2, Lx/2], [0, 0], [slice_positions{3}, slice_positions{3}], ...
      'g-', 'LineWidth', 2);

xlabel('x (m)'); ylabel('y (m)'); zlabel('z (m)');
title('三维电势切片图 (x=0, y=0, z=H/2)');
axis equal; grid on; view(45, 30);
colorbar;
caxis([min_V, max_V]);

sgtitle('三维电势分布可视化', 'FontSize', 16, 'FontWeight', 'bold');

% 7.3 三维电场分布
fig3 = figure('Position', [100, 100, 1200, 500], 'Name', '三维电场分布');
fig_handles = [fig_handles, fig3];

% 子图1：三维电场强度等值面
subplot(1, 2, 1);
hold on;

% 计算电场强度等值面
E_min_val = min(E_mag(:));
E_max_val = max_E;
E_range = E_max_val - E_min_val;
E_isovalues = E_min_val + E_range * [0.3, 0.5, 0.7];

% 获取hot颜色映射
num_E_isos = length(E_isovalues);
E_cmap = hot(num_E_isos + 2); % 多取一些颜色

for i = 1:num_E_isos
    isoval = E_isovalues(i);
    
    % 提取等值面
    fv = isosurface(X, Y, Z, E_mag, isoval);
    
    if ~isempty(fv.vertices)
        p = patch(fv);
        % 使用正确的颜色 - 从hot颜色映射中获取
        set(p, 'FaceColor', E_cmap(i+1, :), ...
               'EdgeColor', 'none', 'FaceAlpha', 0.4);
    end
end

% 绘制避雷针
[x_cyl, y_cyl, z_cyl] = cylinder(R_base, 30);
z_cyl = z_cyl * H_cylinder;
surf(x_cyl, y_cyl, z_cyl, 'FaceColor', [0.3, 0.3, 0.3], ...
     'EdgeColor', 'none', 'FaceAlpha', 0.7);

[x_cone, y_cone, z_cone] = cylinder([R_base, 0.001], 30);
z_cone = z_cone * H_cone + H_cylinder;
surf(x_cone, y_cone, z_cone, 'FaceColor', [0.5, 0.5, 0.5], ...
     'EdgeColor', 'none', 'FaceAlpha', 0.7);

% 标记最大电场位置
plot3(max_E_x, max_E_y, max_E_z, 'rp', 'MarkerSize', 15, ...
      'MarkerFaceColor', 'r', 'MarkerEdgeColor', 'k');
text(max_E_x, max_E_y, max_E_z+0.2, ...
     sprintf('E_{max}=%.2e V/m', max_E), ...
     'HorizontalAlignment', 'center', 'FontWeight', 'bold');

xlabel('x (m)'); ylabel('y (m)'); zlabel('z (m)');
title(sprintf('三维电场强度分布 (\\theta = %.0f°)', theta_deg));
axis equal; grid on; view(45, 30);
light('Position', [1, 1, 2], 'Style', 'infinite');
lighting gouraud;
camlight('headlight');
colorbar;

% 子图2：三维电场矢量图
subplot(1, 2, 2);
hold on;

% 在避雷针附近区域采样显示电场矢量
% 定义采样区域（避雷针附近）
x_range_idx = find(abs(x) <= R_base*5);
y_range_idx = find(abs(y) <= R_base*5);
z_range_idx = find(z <= H_total*1.5);

% 确保索引不超出范围
x_range_idx = x_range_idx(x_range_idx >= 1 & x_range_idx <= Nx);
y_range_idx = y_range_idx(y_range_idx >= 1 & y_range_idx <= Ny);
z_range_idx = z_range_idx(z_range_idx >= 1 & z_range_idx <= Nz);

if isempty(x_range_idx) || isempty(y_range_idx) || isempty(z_range_idx)
    % 如果找不到合适的索引，使用整个区域
    x_range_idx = 1:Nx;
    y_range_idx = 1:Ny;
    z_range_idx = 1:Nz;
end

% 进一步降采样
skip = 6;
if length(x_range_idx) > skip
    x_idx_sampled = x_range_idx(1:skip:end);
else
    x_idx_sampled = x_range_idx;
end

if length(y_range_idx) > skip
    y_idx_sampled = y_range_idx(1:skip:end);
else
    y_idx_sampled = y_range_idx;
end

if length(z_range_idx) > skip
    z_idx_sampled = z_range_idx(1:skip:end);
else
    z_idx_sampled = z_range_idx;
end

% 提取采样数据
X_sampled = X(y_idx_sampled, x_idx_sampled, z_idx_sampled);
Y_sampled = Y(y_idx_sampled, x_idx_sampled, z_idx_sampled);
Z_sampled = Z(y_idx_sampled, x_idx_sampled, z_idx_sampled);
Ex_sampled = Ex(y_idx_sampled, x_idx_sampled, z_idx_sampled);
Ey_sampled = Ey(y_idx_sampled, x_idx_sampled, z_idx_sampled);
Ez_sampled = Ez(y_idx_sampled, x_idx_sampled, z_idx_sampled);

% 绘制电场矢量
if ~isempty(X_sampled) && ~isempty(Ex_sampled)
    % 归一化矢量长度以便显示
    vector_magnitudes = sqrt(Ex_sampled.^2 + Ey_sampled.^2 + Ez_sampled.^2);
    max_vector = max(vector_magnitudes(:));
    
    if max_vector > 0
        scale_factor = 0.5 / max_vector;
        Ex_sampled_scaled = Ex_sampled * scale_factor;
        Ey_sampled_scaled = Ey_sampled * scale_factor;
        Ez_sampled_scaled = Ez_sampled * scale_factor;
        
        quiver3(X_sampled, Y_sampled, Z_sampled, ...
                Ex_sampled_scaled, Ey_sampled_scaled, Ez_sampled_scaled, ...
                'k', 'LineWidth', 1, 'MaxHeadSize', 0.3);
    else
        text(0, 0, H_total/2, '电场矢量太小', ...
             'HorizontalAlignment', 'center', 'FontSize', 12);
    end
else
    text(0, 0, H_total/2, '无法提取电场矢量数据', ...
         'HorizontalAlignment', 'center', 'FontSize', 12);
end

% 绘制避雷针
[x_cyl, y_cyl, z_cyl] = cylinder(R_base, 30);
z_cyl = z_cyl * H_cylinder;
surf(x_cyl, y_cyl, z_cyl, 'FaceColor', [0.3, 0.3, 0.3], ...
     'EdgeColor', 'none', 'FaceAlpha', 0.7);

[x_cone, y_cone, z_cone] = cylinder([R_base, 0.001], 30);
z_cone = z_cone * H_cone + H_cylinder;
surf(x_cone, y_cone, z_cone, 'FaceColor', [0.5, 0.5, 0.5], ...
     'EdgeColor', 'none', 'FaceAlpha', 0.7);

% 添加电场线起始点（在避雷针尖端附近）
num_streamlines = 20;
for i = 1:num_streamlines
    % 在避雷针尖端附近随机选择起始点
    startx = (rand-0.5) * R_base * 2;
    starty = (rand-0.5) * R_base * 2;
    startz = H_total + 0.01;
    
    % 简单的电场线追踪（简化版本）
    plot3(startx, starty, startz, 'bo', 'MarkerSize', 5, ...
          'MarkerFaceColor', 'b');
end

xlabel('x (m)'); ylabel('y (m)'); zlabel('z (m)');
title('三维电场矢量分布（避雷针附近）');
axis equal; grid on; view(45, 30);
xlim([-R_base*6, R_base*6]);
ylim([-R_base*6, R_base*6]);
zlim([0, H_total*1.2]);

sgtitle('三维电场分布可视化', 'FontSize', 16, 'FontWeight', 'bold');

% 7.4 避雷针尖端附近的详细视图（二维截面，y=0平面）
fig4 = figure('Position', [100, 100, 1200, 500], 'Name', '避雷针尖端附近详细分布');
fig_handles = [fig_handles, fig4];

% 找到y=0的索引
[~, y0_idx] = min(abs(y));

% 定义只包含圆锥部分的区域
z_cone_start = H_cylinder * 0.9;  % 从圆柱顶部稍下开始
z_cone_end = H_total * 1.1;       % 到圆锥尖端稍上结束

% 找到对应的z索引范围
z_start_idx = find(z >= z_cone_start, 1);
z_end_idx = find(z <= z_cone_end, 1, 'last');

% 限制x范围以关注避雷针附近
x_limit = R_base * 4;
x_start_idx = find(x >= -x_limit, 1);
x_end_idx = find(x <= x_limit, 1, 'last');

% 确保索引有效
if isempty(z_start_idx) || isempty(z_end_idx) || ...
   isempty(x_start_idx) || isempty(x_end_idx) || ...
   z_start_idx > z_end_idx || x_start_idx > x_end_idx
    
    fprintf('  警告: 无法提取圆锥部分数据，使用完整数据\n');
    x_start_idx = 1;
    x_end_idx = Nx;
    z_start_idx = 1;
    z_end_idx = Nz;
end

% 提取y=0截面的圆锥部分数据
V_cone = squeeze(V(y0_idx, x_start_idx:x_end_idx, z_start_idx:z_end_idx));
X_cone = squeeze(X(y0_idx, x_start_idx:x_end_idx, z_start_idx:z_end_idx));
Z_cone = squeeze(Z(y0_idx, x_start_idx:x_end_idx, z_start_idx:z_end_idx));
Ex_cone = squeeze(Ex(y0_idx, x_start_idx:x_end_idx, z_start_idx:z_end_idx));
Ez_cone = squeeze(Ez(y0_idx, x_start_idx:x_end_idx, z_start_idx:z_end_idx));
E_mag_cone = squeeze(E_mag(y0_idx, x_start_idx:x_end_idx, z_start_idx:z_end_idx));

% 检查数据是否为空
if isempty(V_cone) || all(isnan(V_cone(:)))
    fprintf('  错误: 圆锥部分数据为空或全为NaN，使用完整数据\n');
    % 使用完整数据作为后备
    V_cone = squeeze(V(y0_idx, :, :));
    X_cone = squeeze(X(y0_idx, :, :));
    Z_cone = squeeze(Z(y0_idx, :, :));
    Ex_cone = squeeze(Ex(y0_idx, :, :));
    Ez_cone = squeeze(Ez(y0_idx, :, :));
    E_mag_cone = squeeze(E_mag(y0_idx, :, :));
end

% 子图1：电势分布 + 等势线
subplot(1, 3, 1);
% 绘制电势分布
contourf(X_cone, Z_cone, V_cone, 30, 'LineStyle', 'none');
hold on;

% 添加50条等势线
if any(~isnan(V_cone(:))) && ~all(V_cone(:) == V_cone(1))
    contour(X_cone, Z_cone, V_cone, 50, 'k', 'LineWidth', 0.5, 'ShowText', 'off');
end

% 绘制圆锥部分
x_cone_boundary = linspace(-R_base, R_base, 100);
z_cone_boundary = H_cylinder + (H_cone/R_base) * (R_base - abs(x_cone_boundary));
plot(x_cone_boundary, z_cone_boundary, 'k-', 'LineWidth', 3);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 3);

% 标记尖端
plot(0, H_total, 'ro', 'MarkerSize', 10, 'MarkerFaceColor', 'r');

xlabel('x (m)'); ylabel('z (m)');
title('圆锥部分电势分布与等势线');
colorbar;
axis tight; grid on;

% 子图2：电场强度分布 + 等势线
subplot(1, 3, 2);
% 绘制电场强度分布
contourf(X_cone, Z_cone, E_mag_cone, 30, 'LineStyle', 'none');
hold on;
colorbar;
colormap hot;

% 添加等势线
if any(~isnan(V_cone(:))) && ~all(V_cone(:) == V_cone(1))
    contour(X_cone, Z_cone, V_cone, 20, 'w', 'LineWidth', 0.8, 'ShowText', 'off');
end

% 绘制圆锥部分
plot(x_cone_boundary, z_cone_boundary, 'k-', 'LineWidth', 3);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 3);

% 标记尖端
plot(0, H_total, 'ro', 'MarkerSize', 10, 'MarkerFaceColor', 'r');

xlabel('x (m)'); ylabel('z ( m)');
title('圆锥部分电场强度与等势线');
axis tight; grid on;

% 子图3：电场矢量 + 等势线
subplot(1, 3, 3);
% 绘制电势分布背景
contourf(X_cone, Z_cone, V_cone, 30, 'LineStyle', 'none');
hold on;
colorbar;
colormap jet;

% 添加等势线
if any(~isnan(V_cone(:))) && ~all(V_cone(:) == V_cone(1))
    contour(X_cone, Z_cone, V_cone, 20, 'k', 'LineWidth', 0.8, 'ShowText', 'off');
end

% 添加电场矢量 - 确保数据有效
if ~isempty(Ex_cone) && ~isempty(Ez_cone) && ...
   any(Ex_cone(:) ~= 0) && any(Ez_cone(:) ~= 0)
    
    % 进一步降低采样率
    skip2 = 4;
    if size(X_cone, 1) > skip2 && size(X_cone, 2) > skip2
        x_indices = 1:skip2:size(X_cone, 1);
        z_indices = 1:skip2:size(X_cone, 2);
        
        X_sampled = X_cone(x_indices, z_indices);
        Z_sampled = Z_cone(x_indices, z_indices);
        Ex_sampled = Ex_cone(x_indices, z_indices);
        Ez_sampled = Ez_cone(x_indices, z_indices);
        
        % 归一化矢量长度以便显示
        max_vector = max(sqrt(Ex_sampled(:).^2 + Ez_sampled(:).^2));
        if max_vector > 0
            scale_factor = 0.02 / max_vector;
            Ex_sampled = Ex_sampled * scale_factor;
            Ez_sampled = Ez_sampled * scale_factor;
        end
        
        quiver(X_sampled, Z_sampled, Ex_sampled, Ez_sampled, 0.5, ...
               'w', 'LineWidth', 1.2, 'MaxHeadSize', 0.5);
    else
        % 如果数据太小，直接绘制
        quiver(X_cone, Z_cone, Ex_cone, Ez_cone, 0.5, ...
               'w', 'LineWidth', 1.2, 'MaxHeadSize', 0.5);
    end
else
    fprintf('  警告: 电场矢量数据为空或全零\n');
    text(mean(xlim), mean(ylim), '电场矢量数据为空', ...
         'HorizontalAlignment', 'center', 'FontSize', 12, 'Color', 'red');
end

% 绘制圆锥部分
plot(x_cone_boundary, z_cone_boundary, 'k-', 'LineWidth', 3);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 3);

% 标记尖端
plot(0, H_total, 'ro', 'MarkerSize', 10, 'MarkerFaceColor', 'r');

xlabel('x (m)'); ylabel('z (m)');
title('圆锥部分电场矢量与等势线');
axis tight; grid on;

sgtitle(sprintf('避雷针尖端附近详细分布 (θ = %.0f°)', theta_deg), 'FontSize', 16, 'FontWeight', 'bold');

% 7.5 二维截面图（x=0, y=0, z=H_total/2）
% x=0截面
fig5 = figure('Position', [100, 100, 800, 600], 'Name', 'x=0截面电势与电场分布');
fig_handles = [fig_handles, fig5];

% 找到x=0的索引
[~, x0_idx] = min(abs(x));

% 提取x=0截面的数据
V_slice_x0 = squeeze(V(:, x0_idx, :));
Y_slice_x0 = squeeze(Y(:, x0_idx, :));
Z_slice_x0 = squeeze(Z(:, x0_idx, :));
Ey_slice_x0 = squeeze(Ey(:, x0_idx, :));
Ez_slice_x0 = squeeze(Ez(:, x0_idx, :));

% 子图1：电势分布
subplot(2, 2, 1);
contourf(Y_slice_x0, Z_slice_x0, V_slice_x0, 50, 'LineStyle', 'none');
hold on;
% 添加等势线
contour(Y_slice_x0, Z_slice_x0, V_slice_x0, 50, 'k', 'LineWidth', 0.5);
% 绘制避雷针轮廓
rectangle('Position', [-R_base, 0, 2*R_base, H_cylinder], ...
          'FaceColor', [0.3, 0.3, 0.3, 0.5], 'EdgeColor', 'k', 'LineWidth', 2);
y_cone = linspace(-R_base, R_base, 100);
z_cone = H_cylinder + (H_cone/R_base) * (R_base - abs(y_cone));
plot(y_cone, z_cone, 'k-', 'LineWidth', 2);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 2);
colorbar;
xlabel('y (m)'); ylabel('z (m)');
title('x=0截面电势分布 (50条等势线)');
axis tight; grid on;

% 子图2：电场矢量
subplot(2, 2, 2);
% 降低采样率
skip3 = 6;
if size(Y_slice_x0, 1) > skip3 && size(Y_slice_x0, 2) > skip3
    y_indices = 1:skip3:size(Y_slice_x0, 1);
    z_indices = 1:skip3:size(Y_slice_x0, 2);
    Y_sampled = Y_slice_x0(y_indices, z_indices);
    Z_sampled = Z_slice_x0(y_indices, z_indices);
    Ey_sampled = Ey_slice_x0(y_indices, z_indices);
    Ez_sampled = Ez_slice_x0(y_indices, z_indices);
    
    % 归一化
    max_vec = max(sqrt(Ey_sampled(:).^2 + Ez_sampled(:).^2));
    if max_vec > 0
        scale = 0.03 / max_vec;
        Ey_sampled = Ey_sampled * scale;
        Ez_sampled = Ez_sampled * scale;
    end
    
    contourf(Y_slice_x0, Z_slice_x0, V_slice_x0, 30, 'LineStyle', 'none');
    hold on;
    quiver(Y_sampled, Z_sampled, Ey_sampled, Ez_sampled, 0.5, ...
           'w', 'LineWidth', 1.2, 'MaxHeadSize', 0.5);
else
    contourf(Y_slice_x0, Z_slice_x0, V_slice_x0, 30, 'LineStyle', 'none');
    text(mean(xlim), mean(ylim), '电场矢量数据不足', ...
         'HorizontalAlignment', 'center', 'FontSize', 12);
end

% 绘制避雷针轮廓
rectangle('Position', [-R_base, 0, 2*R_base, H_cylinder], ...
          'FaceColor', [0.3, 0.3, 0.3, 0.3], 'EdgeColor', 'k', 'LineWidth', 1);
plot(y_cone, z_cone, 'k-', 'LineWidth', 2);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 2);
colorbar;
xlabel('y (m)'); ylabel('z (m)');
title('x=0截面电场矢量');
axis tight; grid on;

% 子图3：电场强度分布
subplot(2, 2, 3);
E_mag_slice_x0 = sqrt(Ey_slice_x0.^2 + Ez_slice_x0.^2);
contourf(Y_slice_x0, Z_slice_x0, E_mag_slice_x0, 30, 'LineStyle', 'none');
hold on;
% 绘制避雷针轮廓
rectangle('Position', [-R_base, 0, 2*R_base, H_cylinder], ...
          'FaceColor', [0.3, 0.3, 0.3, 0.3], 'EdgeColor', 'k', 'LineWidth', 1);
plot(y_cone, z_cone, 'k-', 'LineWidth', 2);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 2);
colorbar;
xlabel('y (m)'); ylabel('z (m)');
title('x=0截面电场强度');
axis tight; grid on;

% 子图4：电场线
subplot(2, 2, 4);
contourf(Y_slice_x0, Z_slice_x0, V_slice_x0, 30, 'LineStyle', 'none');
hold on;

% 绘制电场线（简化版本）
start_points_y = linspace(-R_base*2, R_base*2, 10);
start_points_z = ones(1,10) * H_total * 1.05;

% 使用streamline函数绘制电场线
try
    streamline(Y_slice_x0, Z_slice_x0, Ey_slice_x0, Ez_slice_x0, ...
               start_points_y, start_points_z);
catch
    % 如果streamline失败，使用简单的quiver替代
    quiver(Y_slice_x0, Z_slice_x0, Ey_slice_x0, Ez_slice_x0, 0.5, ...
           'w', 'LineWidth', 0.5);
end

% 绘制避雷针轮廓
rectangle('Position', [-R_base, 0, 2*R_base, H_cylinder], ...
          'FaceColor', [0.3, 0.3, 0.3, 0.3], 'EdgeColor', 'k', 'LineWidth', 1);
plot(y_cone, z_cone, 'k-', 'LineWidth', 2);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 2);
colorbar;
xlabel('y (m)'); ylabel('z (m)');
title('x=0截面电场线');
axis tight; grid on;

sgtitle('x=0截面电势与电场分布', 'FontSize', 14, 'FontWeight', 'bold');

% 创建y=0截面图
fig6 = figure('Position', [100, 100, 800, 600], 'Name', 'y=0截面电势与电场分布');
fig_handles = [fig_handles, fig6];

% 提取y=0截面的数据
V_slice_y0 = squeeze(V(y0_idx, :, :));
X_slice_y0 = squeeze(X(y0_idx, :, :));
Z_slice_y0 = squeeze(Z(y0_idx, :, :));
Ex_slice_y0 = squeeze(Ex(y0_idx, :, :));
Ez_slice_y0 = squeeze(Ez(y0_idx, :, :));

% 子图1：电势分布
subplot(2, 2, 1);
contourf(X_slice_y0, Z_slice_y0, V_slice_y0, 50, 'LineStyle', 'none');
hold on;
% 添加等势线
contour(X_slice_y0, Z_slice_y0, V_slice_y0, 50, 'k', 'LineWidth', 0.5);
% 绘制避雷针轮廓
rectangle('Position', [-R_base, 0, 2*R_base, H_cylinder], ...
          'FaceColor', [0.3, 0.3, 0.3, 0.5], 'EdgeColor', 'k', 'LineWidth', 2);
x_cone = linspace(-R_base, R_base, 100);
z_cone = H_cylinder + (H_cone/R_base) * (R_base - abs(x_cone));
plot(x_cone, z_cone, 'k-', 'LineWidth', 2);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 2);
colorbar;
xlabel('x (m)'); ylabel('z (m)');
title('y=0截面电势分布 (50条等势线)');
axis tight; grid on;

% 子图2：电场矢量
subplot(2, 2, 2);
% 降低采样率
if size(X_slice_y0, 1) > skip3 && size(X_slice_y0, 2) > skip3
    x_indices = 1:skip3:size(X_slice_y0, 1);
    z_indices = 1:skip3:size(X_slice_y0, 2);
    X_sampled = X_slice_y0(x_indices, z_indices);
    Z_sampled = Z_slice_y0(x_indices, z_indices);
    Ex_sampled = Ex_slice_y0(x_indices, z_indices);
    Ez_sampled = Ez_slice_y0(x_indices, z_indices);
    
    % 归一化
    max_vec = max(sqrt(Ex_sampled(:).^2 + Ez_sampled(:).^2));
    if max_vec > 0
        scale = 0.03 / max_vec;
        Ex_sampled = Ex_sampled * scale;
        Ez_sampled = Ez_sampled * scale;
    end
    
    contourf(X_slice_y0, Z_slice_y0, V_slice_y0, 30, 'LineStyle', 'none');
    hold on;
    quiver(X_sampled, Z_sampled, Ex_sampled, Ez_sampled, 0.5, ...
           'w', 'LineWidth', 1.2, 'MaxHeadSize', 0.5);
else
    contourf(X_slice_y0, Z_slice_y0, V_slice_y0, 30, 'LineStyle', 'none');
    text(mean(xlim), mean(ylim), '电场矢量数据不足', ...
         'HorizontalAlignment', 'center', 'FontSize', 12);
end

% 绘制避雷针轮廓
rectangle('Position', [-R_base, 0, 2*R_base, H_cylinder], ...
          'FaceColor', [0.3, 0.3, 0.3, 0.3], 'EdgeColor', 'k', 'LineWidth', 1);
plot(x_cone, z_cone, 'k-', 'LineWidth', 2);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 2);
colorbar;
xlabel('x (m)'); ylabel('z (m)');
title('y=0截面电场矢量');
axis tight; grid on;

% 子图3：电场强度分布
subplot(2, 2, 3);
E_mag_slice_y0 = sqrt(Ex_slice_y0.^2 + Ez_slice_y0.^2);
contourf(X_slice_y0, Z_slice_y0, E_mag_slice_y0, 30, 'LineStyle', 'none');
hold on;
% 绘制避雷针轮廓
rectangle('Position', [-R_base, 0, 2*R_base, H_cylinder], ...
          'FaceColor', [0.3, 0.3, 0.3, 0.3], 'EdgeColor', 'k', 'LineWidth', 1);
plot(x_cone, z_cone, 'k-', 'LineWidth', 2);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 2);
colorbar;
xlabel('x (m)'); ylabel('z (m)');
title('y=0截面电场强度');
axis tight; grid on;

% 子图4：电场线
subplot(2, 2, 4);
contourf(X_slice_y0, Z_slice_y0, V_slice_y0, 30, 'LineStyle', 'none');
hold on;
% 绘制电场线（简化版本）
start_points_x = linspace(-R_base*2, R_base*2, 10);
start_points_z = ones(1,10) * H_total * 1.05;

% 使用streamline函数绘制电场线
try
    streamline(X_slice_y0, Z_slice_y0, Ex_slice_y0, Ez_slice_y0, ...
               start_points_x, start_points_z);
catch
    % 如果streamline失败，使用简单的quiver替代
    quiver(X_slice_y0, Z_slice_y0, Ex_slice_y0, Ez_slice_y0, 0.5, ...
           'w', 'LineWidth', 0.5);
end

% 绘制避雷针轮廓
rectangle('Position', [-R_base, 0, 2*R_base, H_cylinder], ...
          'FaceColor', [0.3, 0.3, 0.3, 0.3], 'EdgeColor', 'k', 'LineWidth', 1);
plot(x_cone, z_cone, 'k-', 'LineWidth', 2);
plot([-R_base, R_base], [H_total, H_total], 'k-', 'LineWidth', 2);
colorbar;
xlabel('x (m)'); ylabel('z (m)');
title('y=0截面电场线');
axis tight; grid on;

sgtitle('y=0截面电势与电场分布', 'FontSize', 14, 'FontWeight', 'bold');

% 创建z=H_total/2截面图
fig7 = figure('Position', [100, 100, 800, 600], 'Name', sprintf('z=%.2f_m截面电势与电场分布', H_total/2));
fig_handles = [fig_handles, fig7];

% 找到z=H_total/2的索引
[~, z_mid_idx] = min(abs(z - H_total/2));

% 提取z=H_total/2截面的数据
V_slice_z = squeeze(V(:, :, z_mid_idx));
X_slice_z = squeeze(X(:, :, z_mid_idx));
Y_slice_z = squeeze(Y(:, :, z_mid_idx));
Ex_slice_z = squeeze(Ex(:, :, z_mid_idx));
Ey_slice_z = squeeze(Ey(:, :, z_mid_idx));

% 子图1：电势分布
subplot(2, 2, 1);
contourf(X_slice_z, Y_slice_z, V_slice_z, 50, 'LineStyle', 'none');
hold on;
% 添加等势线
contour(X_slice_z, Y_slice_z, V_slice_z, 50, 'k', 'LineWidth', 0.5);

% 绘制避雷针截面
if z(z_mid_idx) <= H_total
    if z(z_mid_idx) <= H_cylinder
        % 圆柱部分
        viscircles([0, 0], R_base, 'Color', 'k', 'LineWidth', 2);
    else
        % 圆锥部分
        r_current = R_base * (H_total - z(z_mid_idx)) / H_cone;
        viscircles([0, 0], r_current, 'Color', 'k', 'LineWidth', 2);
    end
end

colorbar;
xlabel('x (m)'); ylabel('y (m)');
title(sprintf('z=%.2f m截面电势分布 (50条等势线)', z(z_mid_idx)));
axis equal; grid on;

% 子图2：电场矢量
subplot(2, 2, 2);
% 降低采样率
if size(X_slice_z, 1) > skip3 && size(X_slice_z, 2) > skip3
    x_indices = 1:skip3:size(X_slice_z, 1);
    y_indices = 1:skip3:size(X_slice_z, 2);
    X_sampled = X_slice_z(x_indices, y_indices);
    Y_sampled = Y_slice_z(x_indices, y_indices);
    Ex_sampled = Ex_slice_z(x_indices, y_indices);
    Ey_sampled = Ey_slice_z(x_indices, y_indices);
    
    % 归一化
    max_vec = max(sqrt(Ex_sampled(:).^2 + Ey_sampled(:).^2));
    if max_vec > 0
        scale = 0.03 / max_vec;
        Ex_sampled = Ex_sampled * scale;
        Ey_sampled = Ey_sampled * scale;
    end
    
    contourf(X_slice_z, Y_slice_z, V_slice_z, 30, 'LineStyle', 'none');
    hold on;
    quiver(X_sampled, Y_sampled, Ex_sampled, Ey_sampled, 0.5, ...
           'w', 'LineWidth', 1.2, 'MaxHeadSize', 0.5);
else
    contourf(X_slice_z, Y_slice_z, V_slice_z, 30, 'LineStyle', 'none');
    text(mean(xlim), mean(ylim), '电场矢量数据不足', ...
         'HorizontalAlignment', 'center', 'FontSize', 12);
end

% 绘制避雷针截面
if z(z_mid_idx) <= H_total
    if z(z_mid_idx) <= H_cylinder
        viscircles([0, 0], R_base, 'Color', 'k', 'LineWidth', 2);
    else
        r_current = R_base * (H_total - z(z_mid_idx)) / H_cone;
        viscircles([0, 0], r_current, 'Color', 'k', 'LineWidth', 2);
    end
end

colorbar;
xlabel('x (m)'); ylabel('y (m)');
title(sprintf('z=%.2f m截面电场矢量', z(z_mid_idx)));
axis equal; grid on;

% 子图3：电场强度分布
subplot(2, 2, 3);
E_mag_slice_z = sqrt(Ex_slice_z.^2 + Ey_slice_z.^2);
contourf(X_slice_z, Y_slice_z, E_mag_slice_z, 30, 'LineStyle', 'none');
hold on;

% 绘制避雷针截面
if z(z_mid_idx) <= H_total
    if z(z_mid_idx) <= H_cylinder
        viscircles([0, 0], R_base, 'Color', 'k', 'LineWidth', 2);
    else
        r_current = R_base * (H_total - z(z_mid_idx)) / H_cone;
        viscircles([0, 0], r_current, 'Color', 'k', 'LineWidth', 2);
    end
end

colorbar;
xlabel('x (m)'); ylabel('y (m)');
title(sprintf('z=%.2f m截面电场强度', z(z_mid_idx)));
axis equal; grid on;

% 子图4：电场线
subplot(2, 2, 4);
contourf(X_slice_z, Y_slice_z, V_slice_z, 30, 'LineStyle', 'none');
hold on;

% 绘制电场线起始点
start_points_x = linspace(-R_base*2, R_base*2, 8);
start_points_y = linspace(-R_base*2, R_base*2, 8);
[X_start, Y_start] = meshgrid(start_points_x, start_points_y);
X_start = X_start(:);
Y_start = Y_start(:);

% 使用streamline函数绘制电场线
try
    streamline(X_slice_z, Y_slice_z, Ex_slice_z, Ey_slice_z, ...
               X_start, Y_start);
catch
    % 如果streamline失败，使用简单的quiver替代
    quiver(X_slice_z, Y_slice_z, Ex_slice_z, Ey_slice_z, 0.5, ...
           'w', 'LineWidth', 0.5);
end

% 绘制避雷针截面
if z(z_mid_idx) <= H_total
    if z(z_mid_idx) <= H_cylinder
        viscircles([0, 0], R_base, 'Color', 'k', 'LineWidth', 2);
    else
        r_current = R_base * (H_total - z(z_mid_idx)) / H_cone;
        viscircles([0, 0], r_current, 'Color', 'k', 'LineWidth', 2);
    end
end

colorbar;
xlabel('x (m)'); ylabel('y (m)');
title(sprintf('z=%.2f m截面电场线', z(z_mid_idx)));
axis equal; grid on;

sgtitle(sprintf('z=%.2f m截面电势与电场分布', z(z_mid_idx)), 'FontSize', 14, 'FontWeight', 'bold');

% 7.6 轴向和径向分布曲线
fig8 = figure('Position', [100, 100, 1000, 400], 'Name', '轴向与径向分布');
fig_handles = [fig_handles, fig8];

% 轴向分布
subplot(1, 2, 1);
x_center_idx = find(abs(x) == min(abs(x)), 1);
y_center_idx = find(abs(y) == min(abs(y)), 1);

V_axis = squeeze(V(y_center_idx, x_center_idx, :));
E_axis = squeeze(E_mag(y_center_idx, x_center_idx, :));

yyaxis left;
plot(z, V_axis, 'b-', 'LineWidth', 2);
ylabel('电势 V (V)');
xlabel('高度 z (m)');
yyaxis right;
plot(z, E_axis, 'r-', 'LineWidth', 2);
ylabel('电场强度 |E| (V/m)');
title('沿避雷针轴线分布');
grid on; grid minor;

% 标记避雷针范围
hold on;
yyaxis left;
plot([H_cylinder, H_cylinder], ylim, 'k--', 'LineWidth', 1);
plot([H_total, H_total], ylim, 'k--', 'LineWidth', 1);
text(H_cylinder/2, min(V_axis)*0.9, '圆柱段', 'HorizontalAlignment', 'center');
text(H_cylinder + H_cone/2, min(V_axis)*0.9, '圆锥段', 'HorizontalAlignment', 'center');

% 径向分布
subplot(1, 2, 2);
z_positions = [0.5, 1.0, 1.5, 2.0];
colors = lines(length(z_positions));

hold on;
for i = 1:length(z_positions)
    [~, z_idx] = min(abs(z - z_positions(i)));
    V_radial = squeeze(V(y_center_idx, :, z_idx));
    plot(x, V_radial, '-', 'Color', colors(i, :), 'LineWidth', 2, ...
         'DisplayName', sprintf('z=%.1f m', z_positions(i)));
end
xlabel('径向距离 x (m)');
ylabel('电势 V (V)');
title('不同高度的径向电势分布');
grid on; grid minor;
legend('Location', 'best');

% 标记避雷针位置
plot([-R_base, -R_base], ylim, 'k--', 'LineWidth', 1);
plot([R_base, R_base], ylim, 'k--', 'LineWidth', 1);
text(0, max(ylim)*0.9, '避雷针', 'HorizontalAlignment', 'center');

sgtitle('轴向与径向电势分布', 'FontSize', 14, 'FontWeight', 'bold');

%% 8. 数据导出与报告生成
fprintf('\n=== 数据导出与报告生成 ===\n');

% 8.1 保存原始数据到data子目录
data_dir = fullfile(output_dir, 'data');
save(fullfile(data_dir, 'simulation_data.mat'), ...
     'X', 'Y', 'Z', 'V', 'Ex', 'Ey', 'Ez', 'E_mag', ...
     'x', 'y', 'z', 'residual_history', 'iteration_time', ...
     'theta_deg', 'R_base', 'H_cone', 'H_cylinder', 'H_total', ...
     'max_E', 'max_E_x', 'max_E_y', 'max_E_z', ...
     'max_V', 'min_V', 'total_time', '-v7.3');

fprintf('  原始数据已保存至: %s\n', fullfile(data_dir, 'simulation_data.mat'));

% 8.2 保存收敛数据
if ~isempty(residual_history)
    convergence_data = table((1:length(residual_history))', residual_history, ...
                             cumsum(iteration_time(1:length(residual_history))), ...
                             'VariableNames', {'Iteration', 'Residual', 'CumulativeTime'});
    writetable(convergence_data, fullfile(data_dir, 'convergence_history.csv'));
end

% 8.3 保存关键结果
key_results = table;
key_results.Parameter = {'圆锥顶角(theta)'; '底面半径'; '圆锥高度'; '圆柱高度'; '总高度'; ...
                         '最大电场'; '最大电场位置_x'; '最大电场位置_y'; '最大电场位置_z'; ...
                         '最大电势'; '最小电势'; '总迭代次数'; '最终残差'; '总计算时间'};
key_results.Value = [theta_deg; R_base; H_cone; H_cylinder; H_total; ...
                     max_E; max_E_x; max_E_y; max_E_z; ...
                     max_V; min_V; length(residual_history); residual_history(end); total_time];
key_results.Unit = {'度'; 'm'; 'm'; 'm'; 'm'; ...
                    'V/m'; 'm'; 'm'; 'm'; ...
                    'V'; 'V'; ''; 'V'; '秒'};

writetable(key_results, fullfile(data_dir, 'key_results.csv'));

% 8.4 保存轴线分布数据
axis_data = table(z', V_axis, E_axis, ...
                  'VariableNames', {'z', 'Potential', 'ElectricField'});
writetable(axis_data, fullfile(data_dir, 'axis_distribution.csv'));

% 8.5 保存径向分布数据
radial_data = table;
for i = 1:length(z_positions)
    [~, z_idx] = min(abs(z - z_positions(i)));
    V_radial = squeeze(V(y_center_idx, :, z_idx));
    E_radial = squeeze(E_mag(y_center_idx, :, z_idx));
    
    temp_table = table(x', V_radial', E_radial', ...
                       'VariableNames', {sprintf('x_z%.1f', z_positions(i)), ...
                                         sprintf('V_z%.1f', z_positions(i)), ...
                                         sprintf('E_z%.1f', z_positions(i))});
    if i == 1
        radial_data = temp_table;
    else
        radial_data = [radial_data, temp_table(:, 2:3)];
    end
end
writetable(radial_data, fullfile(data_dir, 'radial_distribution.csv'));

% 8.6 生成仿真报告到reports子目录
reports_dir = fullfile(output_dir, 'reports');
report_file = fullfile(reports_dir, 'simulation_report.txt');
fid = fopen(report_file, 'w');
if fid ~= -1
    fprintf(fid, '========================================\n');
    fprintf(fid, '       避雷针电场分布仿真报告\n');
    fprintf(fid, '         (自动递增文件夹版本)\n');
    fprintf(fid, '========================================\n\n');
    
    fprintf(fid, '模拟时间: %s\n', datestr(now));
    fprintf(fid, 'MATLAB版本: %s\n\n', version);
    
    fprintf(fid, '1. 输出目录信息\n');
    fprintf(fid, '   主目录: %s\n', output_dir);
    fprintf(fid, '   数据子目录: %s\n', data_dir);
    fprintf(fid, '   报告子目录: %s\n', reports_dir);
    fprintf(fid, '   图形子目录: %s\n', fullfile(output_dir, 'figures'));
    fprintf(fid, '   绘图子目录: %s\n\n', fullfile(output_dir, 'plots'));
    
    fprintf(fid, '2. 模型参数\n');
    fprintf(fid, '   圆锥顶角 theta: %.1f° (%.3f rad)\n', theta_deg, theta);
    fprintf(fid, '   底面半径: %.3f m (1.5 cm)\n', R_base);
    fprintf(fid, '   圆锥高度: %.3f m\n', H_cone);
    fprintf(fid, '   圆柱高度: %.3f m\n', H_cylinder);
    fprintf(fid, '   避雷针总高: %.3f m\n\n', H_total);
    
    fprintf(fid, '3. 仿真区域与网格\n');
    fprintf(fid, '   仿真区域尺寸: %.1f × %.1f × %.1f m³\n', Lx, Ly, Lz);
    fprintf(fid, '   网格尺寸: %d × %d × %d 节点\n', Nx, Ny, Nz);
    fprintf(fid, '   总网格点数: %d\n', Nx*Ny*Nz);
    fprintf(fid, '   边界条件:\n');
    fprintf(fid, '     上底面 (z=%.1f m): %.1e V\n', Lz, V_top);
    fprintf(fid, '     下底面 (z=0 m): %.1e V\n', V_bottom);
    fprintf(fid, '     避雷针表面: %.1e V (接地)\n\n', V_conductor);
    
    fprintf(fid, '4. 数值求解\n');
    fprintf(fid, '   求解方法: 有限差分法 (三维拉普拉斯方程)\n');
    fprintf(fid, '   离散格式: 中心差分，均匀网格\n');
    fprintf(fid, '   迭代方法: 超松弛迭代法 (SOR) with Checkerboard顺序\n');
    fprintf(fid, '   松弛因子: %.2f\n', omega);
    fprintf(fid, '   最大迭代次数: %d\n', max_iter);
    fprintf(fid, '   收敛容差: %.1e\n', tolerance);
    fprintf(fid, '   实际迭代次数: %d\n', length(residual_history));
    fprintf(fid, '   最终残差: %.3e V\n', residual_history(end));
    fprintf(fid, '   总计算时间: %.2f 秒\n\n', total_time);
    
    fprintf(fid, '5. 关键物理结果 (θ = %.0f°)\n', theta_deg);
    fprintf(fid, '   5.1 电场分布\n');
    fprintf(fid, '       最大电场强度: %.3e V/m\n', max_E);
    fprintf(fid, '       最大电场位置: (%.3f, %.3f, %.3f) m\n', max_E_x, max_E_y, max_E_z);
    fprintf(fid, '       避雷针尖端电场: %.3e V/m\n', E_tip);
    
    fprintf(fid, '\n   5.2 电势分布\n');
    fprintf(fid, '       最大电势: %.3e V\n', max_V);
    fprintf(fid, '       最小电势: %.3e V\n', min_V);
    fprintf(fid, '       电势范围: %.3e 到 %.3e V\n\n', min_V, max_V);
    
    fprintf(fid, '6. 可视化输出说明\n');
    fprintf(fid, '   所有图形已保存到figures子目录，包括:\n');
    fprintf(fid, '     1. 收敛性分析图\n');
    fprintf(fid, '     2. 三维电势分布图\n');
    fprintf(fid, '     3. 三维电场分布图\n');
    fprintf(fid, '     4. 避雷针尖端附近详细分布图\n');
    fprintf(fid, '     5. x=0截面电势与电场分布图\n');
    fprintf(fid, '     6. y=0截面电势与电场分布图\n');
    fprintf(fid, '     7. z=H/2截面电势与电场分布图\n');
    fprintf(fid, '     8. 轴向与径向分布曲线图\n\n');
    
    fprintf(fid, '7. 文件清单\n');
    fprintf(fid, '   7.1 数据文件 (data/):\n');
    fprintf(fid, '       simulation_data.mat      - 原始模拟数据\n');
    fprintf(fid, '       convergence_history.csv  - 收敛历史数据\n');
    fprintf(fid, '       key_results.csv          - 关键结果汇总\n');
    fprintf(fid, '       axis_distribution.csv    - 轴线分布数据\n');
    fprintf(fid, '       radial_distribution.csv  - 径向分布数据\n\n');
    
    fprintf(fid, '   7.2 报告文件 (reports/):\n');
    fprintf(fid, '       simulation_report.txt    - 本报告\n\n');
    
    fprintf(fid, '   7.3 图形文件 (figures/):\n');
    fprintf(fid, '       8个PNG文件和8个FIG文件\n\n');
    
    fprintf(fid, '========================================\n');
    fclose(fid);
    
    fprintf('  仿真报告已生成: %s\n', report_file);
else
    fprintf('  警告: 无法创建报告文件\n');
end

% 8.7 保存所有图形到figures子目录
fprintf('  正在保存所有图形...\n');
figures_dir = fullfile(output_dir, 'figures');
plots_dir = fullfile(output_dir, 'plots');

% 保存为PNG格式（高质量，用于查看）
for i = 1:length(fig_handles)
    fig_name = get(fig_handles(i), 'Name');
    if isempty(fig_name)
        fig_name = sprintf('Figure%d', i);
    end
    % 替换文件名中的非法字符
    fig_name = regexprep(fig_name, '[<>:"/\\|?*]', '_');
    
    % 保存到figures子目录
    png_file = fullfile(figures_dir, [fig_name, '.png']);
    saveas(fig_handles(i), png_file);
    
    % 保存到plots子目录（用于进一步处理）
    fig_file = fullfile(plots_dir, [fig_name, '.fig']);
    saveas(fig_handles(i), fig_file);
    
    fprintf('    已保存: %s (PNG和FIG格式)\n', fig_name);
end

% 8.8 保存参数配置文件
params_file = fullfile(data_dir, 'simulation_parameters.mat');
save(params_file, 'theta_deg', 'R_base', 'H_cone', 'H_cylinder', 'H_total', ...
     'Lx', 'Ly', 'Lz', 'Nx', 'Ny', 'Nz', 'V_top', 'V_bottom', 'V_conductor', ...
     'max_iter', 'tolerance', 'omega', 'output_dir');

fprintf('  参数配置文件已保存: %s\n', params_file);

fprintf('  所有图形已保存至输出目录\n');
fprintf('\n=== 模拟完成 ===\n');
fprintf('所有结果已保存至: %s\n', output_dir);

%% 9. 显示关键结果摘要
fprintf('\n');
fprintf('========================================\n');
fprintf('关键结果摘要 (θ = %.0f°)\n', theta_deg);
fprintf('========================================\n');
fprintf('1. 输出目录: %s\n', output_dir);
fprintf('2. 最大电场强度: %.3e V/m\n', max_E);
fprintf('   位置: (%.3f, %.3f, %.3f) m\n', max_E_x, max_E_y, max_E_z);
fprintf('3. 电势范围: %.3e 到 %.3e V\n', min_V, max_V);
fprintf('4. 数值求解: %d 次迭代, %.2f 秒\n', length(residual_history), total_time);
fprintf('5. 生成文件:\n');
fprintf('   - 数据文件: data/*.mat, *.csv\n');
fprintf('   - 图形文件: figures/*.png, plots/*.fig\n');
fprintf('   - 报告文件: reports/simulation_report.txt\n');
fprintf('========================================\n');

%% 10. 创建目录结构说明文件
dir_info_file = fullfile(output_dir, '目录结构说明.txt');
fid2 = fopen(dir_info_file, 'w');
if fid2 ~= -1
    fprintf(fid2, '避雷针电场模拟结果目录结构说明\n');
    fprintf(fid2, '================================\n\n');
    fprintf(fid2, '主目录: %s\n', output_dir);
    fprintf(fid2, '   ├── data/           - 数据文件目录\n');
    fprintf(fid2, '   │   ├── simulation_data.mat      - 原始模拟数据\n');
    fprintf(fid2, '   │   ├── simulation_parameters.mat - 模拟参数\n');
    fprintf(fid2, '   │   ├── convergence_history.csv  - 收敛历史数据\n');
    fprintf(fid2, '   │   ├── key_results.csv          - 关键结果汇总\n');
    fprintf(fid2, '   │   ├── axis_distribution.csv    - 轴线分布数据\n');
    fprintf(fid2, '   │   └── radial_distribution.csv  - 径向分布数据\n');
    fprintf(fid2, '   │\n');
    fprintf(fid2, '   ├── figures/        - 图形文件目录(PNG格式)\n');
    fprintf(fid2, '   │   ├── 收敛性分析.png\n');
    fprintf(fid2, '   │   ├── 三维电势分布.png\n');
    fprintf(fid2, '   │   ├── 三维电场分布.png\n');
    fprintf(fid2, '   │   └── ... (共8个PNG文件)\n');
    fprintf(fid2, '   │\n');
    fprintf(fid2, '   ├── plots/          - 绘图文件目录(FIG格式，MATLAB可编辑)\n');
    fprintf(fid2, '   │   ├── 收敛性分析.fig\n');
    fprintf(fid2, '   │   ├── 三维电势分布.fig\n');
    fprintf(fid2, '   │   ├── 三维电场分布.fig\n');
    fprintf(fid2, '   │   └── ... (共8个FIG文件)\n');
    fprintf(fid2, '   │\n');
    fprintf(fid2, '   ├── reports/        - 报告文件目录\n');
    fprintf(fid2, '   │   └── simulation_report.txt    - 仿真报告\n');
    fprintf(fid2, '   │\n');
    fprintf(fid2, '   └── 目录结构说明.txt  - 本文件\n\n');
    fprintf(fid2, '模拟参数: θ = %.0f°, R = %.3f m, H_total = %.3f m\n', theta_deg, R_base, H_total);
    fprintf(fid2, '模拟时间: %s\n', datestr(now));
    fclose(fid2);
    fprintf('  目录结构说明文件已生成: %s\n', dir_info_file);
end