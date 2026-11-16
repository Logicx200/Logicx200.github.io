clc; clear; close all;

%% 加载数据
headerlines = 8; % 假设没有需要跳过的行
data = readtable('F:\COMSOL\流速数据\定2.0.csv', 'VariableNamingRule', 'preserve', 'HeaderLines', headerlines);

%% 提取变量
x_col_name = data.Properties.VariableNames{1};
y_col_name = data.Properties.VariableNames{2};
z_col_name = data.Properties.VariableNames{3};

%% 参数设置
dt = 0.2; % 时间步长（秒）

%% 获取最上层的z坐标
z = data.(z_col_name);
max_z = max(z);
idx_upper_layer = z == max_z;
upper_layer_data = data(idx_upper_layer, :);

%% 提取最上层的速度数据
unique_x = unique(upper_layer_data.(x_col_name));
unique_y = unique(upper_layer_data.(y_col_name));
[Nx, Ny] = size(meshgrid(unique_x, unique_y)); % 创建网格并获取尺寸

%% 提取速度数据列名
time_labels = {};
time_values = [];
u_tags = {};
v_tags = {};

u_pattern = 'u \(m/s\) @ t=([0-9.]+)';
v_pattern = 'v \(m/s\) @ t=([0-9.]+)';

for col = 4:size(data, 2)
    col_name = data.Properties.VariableNames{col};
    
    matches_u = regexp(col_name, u_pattern, 'tokens');
    matches_v = regexp(col_name, v_pattern, 'tokens');
    
    if ~isempty(matches_u)
        time_str = matches_u{1}{1};
        time_value = str2double(time_str);
        u_tags{end+1} = col_name;
        time_labels{end+1} = time_str;
        time_values(end+1) = time_value;
    elseif ~isempty(matches_v)
        time_str = matches_v{1}{1};
        time_value = str2double(time_str);
        v_tags{end+1} = col_name;
        if ~any(strcmp(time_labels, time_str))
            time_labels{end+1} = time_str;
            time_values(end+1) = time_value;
        end
    end
end

if isempty(time_labels)
    error('未提取到有效的时间标签，请检查列名格式');
end

if isempty(u_tags) || isempty(v_tags)
    error('未提取到速度分量标签，请检查列名格式');
end

[sorted_time_values, sort_indices] = sort(time_values);
time_labels = time_labels(sort_indices);
u_tags = u_tags(sort_indices);
v_tags = v_tags(sort_indices);

%% 创建插值对象并插值
num_time_points = length(time_labels);
u_interp = zeros(Nx, Ny, num_time_points);
v_interp = zeros(Nx, Ny, num_time_points);

[Xq, Yq] = meshgrid(unique_x, unique_y);

for t_idx = 1:num_time_points
    current_t_str = time_labels{t_idx};
    fprintf('处理时间点: %s\n', current_t_str);
    
    u_tag = u_tags{t_idx};
    v_tag = v_tags{t_idx};
    
    % 提取当前时间点的数据
    current_u = upper_layer_data{:, u_tag};
    current_v = upper_layer_data{:, v_tag};
    
    % 检查并清理速度数据
    valid_idx = ~isnan(current_u) & ~isinf(current_u) & ...
                ~isnan(current_v) & ~isinf(current_v);
    
    x_data = upper_layer_data{valid_idx, x_col_name};
    y_data = upper_layer_data{valid_idx, y_col_name};
    current_u = current_u(valid_idx);
    current_v = current_v(valid_idx);
    
    if isempty(x_data) || isempty(y_data)
        warning('时间点 %s 的所有速度数据无效', current_t_str);
        u_interp(:, :, t_idx) = NaN; % 标记无效插值
        v_interp(:, :, t_idx) = NaN;
        continue;
    end
    
    % 检查数据点数量并生成额外点
    [x_data, y_data, current_u, current_v] = ensure_min_points(x_data, y_data, current_u, current_v);
    
    try
        F_u = griddedInterpolant(x_data, y_data, current_u, 'linear', 'extrap');
        F_v = griddedInterpolant(x_data, y_data, current_v, 'linear', 'extrap');
        
        u_interp(:, :, t_idx) = F_u(Xq, Yq);
        v_interp(:, :, t_idx) = F_v(Xq, Yq);
        
    catch ME
        warning('在时间点 %s 进行插值时出错: %s', current_t_str, ME.message);
        u_interp(:, :, t_idx) = NaN; % 标记无效插值
        v_interp(:, :, t_idx) = NaN;
    end
end

% 检查是否有有效的插值结果
valid_time_points = ~all(isnan(u_interp), [1 2]) & ~all(isnan(v_interp), [1 2]);
if ~any(valid_time_points)
    error('所有时间点的插值结果均无效');
end

% 过滤掉无效的时间点
u_interp = u_interp(:, :, valid_time_points);
v_interp = v_interp(:, :, valid_time_points);
time_labels = time_labels(valid_time_points);

%% 确保每个维度至少有两个点的函数
function [x_data, y_data, current_u, current_v] = ensure_min_points(x_data, y_data, current_u, current_v)
    % 确保 x 方向至少有两个点
    unique_x = unique(x_data);
    if length(unique_x) < 2
        x_min = min(unique_x);
        x_max = max(unique_x);
        if x_min == x_max
            x_data = [x_data; x_max + 1e-6]; % 添加一个微小偏移
            y_data = [y_data; mean(unique(y_data))];
            current_u = [current_u; mean(current_u)];
            current_v = [current_v; mean(current_v)];
        else
            x_data = [x_data; linspace(x_min, x_max, 2)];
            y_data = [y_data; mean(unique(y_data))];
            current_u = [current_u; mean(current_u)];
            current_v = [current_v; mean(current_v)];
        end
    end
    
    % 确保 y 方向至少有两个点
    unique_y = unique(y_data);
    if length(unique_y) < 2
        y_min = min(unique_y);
        y_max = max(unique_y);
        if y_min == y_max
            y_data = [y_data; y_max + 1e-6]; % 添加一个微小偏移
            x_data = [x_data; mean(unique(x_data))];
            current_u = [current_u; mean(current_u)];
            current_v = [current_v; mean(current_v)];
        else
            y_data = [y_data; linspace(y_min, y_max, 2)];
            x_data = [x_data; mean(unique(x_data))];
            current_u = [current_u; mean(current_u)];
            current_v = [current_v; mean(current_v)];
        end
    end
end

%% 生成插值结果图
figure;
for t_idx = 1:size(u_interp, 3)
    subplot(1, 2, 1);
    surf(Xq, Yq, u_interp(:, :, t_idx));
    title(['U 分量插值结果 (t = ' time_labels{t_idx} ')']);
    xlabel('X');
    ylabel('Y');
    zlabel('U (m/s)');
    
    subplot(1, 2, 2);
    surf(Xq, Yq, v_interp(:, :, t_idx));
    title(['V 分量插值结果 (t = ' time_labels{t_idx} ')']);
    xlabel('X');
    ylabel('Y');
    zlabel('V (m/s)');
    
    pause(1); % 暂停以便查看结果
end