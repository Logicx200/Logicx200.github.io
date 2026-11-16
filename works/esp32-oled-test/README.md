# ESP32 OLED 测试（工程骨架）

PlatformIO + ESP-IDF 的 ESP32 工程骨架，用于验证开发环境与构建链路，**OLED 显示部分尚未实现**。

## 怎么看
- `src/main.c` 只有 18 字节：`void app_main() {}`，主程序为空，没有 OLED 驱动或显示代码；
- `platformio.ini`：`board = esp32dev`，`framework = espidf`；
- 其余为 PlatformIO 模板文件（`include/`、`lib/`、`test/` 下的 README、`sdkconfig.esp32dev` 等）。

## 说明
- 这是**未完成**的工程：仅验证了 PlatformIO/ESP-IDF 工程能正常构建，不能驱动 OLED；
- 来源机器路径：`C:\Users\x1503\Documents\PlatformIO\Projects\OLED-TEST`；
- 已排除 `.pio/` 构建缓存，其余文件原样保留。
