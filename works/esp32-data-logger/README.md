# ESP32 ADC / UART 数据采集

ESP-IDF v5.x + PlatformIO 工程：用 ESP32 的 ADC 单次采样读取外部电流传感器（ACS758 霍尔电流传感器，GPIO34 / ADC1_CH6），并通过串口（UART0）输出日志与测量结果。

## 怎么跑
- 构建：`pio run`；烧录：`pio run -t upload`；串口监视：`pio device monitor`；
- 需要 ESP32-DevKitC 类开发板 + PlatformIO（`platformio.ini`：`board = esp32dev`，`framework = espidf`）。

## 文件结构
`src/main.c`：ADC 校准与初始化、256 次过采样均值、零点校准、电流换算与串口输出；其余为 `platformio.ini`、`CMakeLists.txt`、`sdkconfig.esp32dev`、`include/`、`lib/`、`test/`、`.vscode/`。

## 说明
- 来源机器路径：`C:\Users\x1503\Documents\PlatformIO\Projects\1`；已排除 `.pio/` 构建缓存与 `.git/`。
- 传感器灵敏度、放大倍数、零点电压等参数需按实际电路在 `main.c` 顶部调整。
