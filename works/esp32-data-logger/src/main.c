// main.c - ESP-IDF v5.5 专用版本，使用最新ADC驱动API
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/uart.h"

// 使用ESP-IDF v5.x的新ADC驱动头文件 [citation:1][citation:10]
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"

// 定义ADC相关参数 (请根据你的硬件电路调整)
#define ADC_UNIT                ADC_UNIT_1          // 使用的ADC单元 (1 或 2)
#define ADC_CHANNEL             ADC_CHANNEL_6       // 你实际连接的GPIO对应的ADC通道 (例如GPIO34对应ADC_CHANNEL_6)
#define ADC_ATTEN               ADC_ATTEN_DB_11     // 11dB衰减，允许输入电压最高约3.6V (根据你的信号电压范围调整)
#define ADC_BITWIDTH            ADC_BITWIDTH_12     // 12位分辨率
#define ADC_READ_LEN            256                 // 过采样/均值滤波的样本数，有助于提高精度
#define ADC_REF_VOLTAGE_MV      3300                // ESP32 ADC参考电压，单位毫伏 (通常为3.3V)

// 定义与传感器及放大电路相关的参数 (必须根据你的实际硬件校准)
#define SENSOR_SENSITIVITY_V_PER_A      0.04f       // ACS758LCB-050B灵敏度: 40mV/A = 0.04 V/A (请核对你的传感器型号)
#define AMPLIFIER_GAIN                  1000.0f     // 外部模拟前端(AFE)的放大倍数。如果未使用放大电路，请设置为1.0。
#define EXPECTED_ZERO_CURRENT_VOLTAGE_MV 1650       // 预期零电流时的电压(mV)。对于5V供电且无放大时通常是2500mV，放大后需要根据你的电路重新测量。

// 全局变量
static const char *TAG = "CurrentMeter";
static adc_oneshot_unit_handle_t adc1_handle = NULL;
static adc_cali_handle_t adc_cali_handle = NULL;
static int s_zero_voltage_mv = EXPECTED_ZERO_CURRENT_VOLTAGE_MV; // 零点电压，将在初始化时校准

// 函数声明
static bool example_adc_calibration_init(adc_unit_t unit, adc_atten_t atten, adc_cali_handle_t *out_handle);
static void adc_init(void);
static float measure_current_ma(void);

/**
 * @brief 初始化ADC校准
 */
static bool example_adc_calibration_init(adc_unit_t unit, adc_atten_t atten, adc_cali_handle_t *out_handle) {
    adc_cali_handle_t handle = NULL;
    esp_err_t ret = ESP_FAIL;
    bool calibrated = false;

    // 使用ESP-IDF v5.x的新校准API，曲线拟合法[citation:1]
    adc_cali_curve_fitting_config_t cali_config = {
        .unit_id = unit,
        .atten = atten,
        .bitwidth = ADC_BITWIDTH,
    };
    ret = adc_cali_create_scheme_curve_fitting(&cali_config, &handle);
    if (ret == ESP_OK) {
        calibrated = true;
    }

    *out_handle = handle;
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "ADC校准方案 (曲线拟合) 初始化成功");
    } else {
        ESP_LOGW(TAG, "ADC校准初始化失败，将使用原始ADC值 (误差较大)");
    }
    return calibrated;
}

/**
 * @brief 初始化ADC硬件和校准
 */
static void adc_init(void) {
    // 1. 配置ADC单次采样单元
    adc_oneshot_unit_init_cfg_t init_config1 = {
        .unit_id = ADC_UNIT,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config1, &adc1_handle));

    // 2. 配置ADC通道
    adc_oneshot_chan_cfg_t config = {
        .atten = ADC_ATTEN,
        .bitwidth = ADC_BITWIDTH,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, ADC_CHANNEL, &config));

    // 3. 初始化ADC校准
    if (example_adc_calibration_init(ADC_UNIT, ADC_ATTEN, &adc_cali_handle) != true) {
        ESP_LOGE(TAG, "警告：无法创建ADC校准句柄，测量值可能存在较大误差");
    }

    // 4. (可选) 执行零点校准。确保此时传感器输入电流为0。
    ESP_LOGI(TAG, "正在进行零点校准，请确保传感器输入电流为0并保持稳定...");
    vTaskDelay(pdMS_TO_TICKS(2000)); // 等待稳定

    int raw_sum = 0;
    int raw_val;
    for (int i = 0; i < 100; i++) {
        ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, ADC_CHANNEL, &raw_val));
        raw_sum += raw_val;
        vTaskDelay(pdMS_TO_TICKS(2));
    }
    int raw_avg = raw_sum / 100;

    if (adc_cali_handle) {
        int voltage_mv;
        ESP_ERROR_CHECK(adc_cali_raw_to_voltage(adc_cali_handle, raw_avg, &voltage_mv));
        s_zero_voltage_mv = voltage_mv;
        ESP_LOGI(TAG, "零点校准完成。ADC原始值：%d，对应零点电压：%d mV", raw_avg, s_zero_voltage_mv);
    } else {
        // 若无校准，使用ADC原始值作为零点参考
        s_zero_voltage_mv = raw_avg;
        ESP_LOGI(TAG, "零点校准完成（未使用电压校准）。ADC原始值：%d", s_zero_voltage_mv);
    }
}

/**
 * @brief 核心测量函数，读取并计算电流值
 * @return 电流值，单位毫安 (mA)
 */
static float measure_current_ma(void) {
    int raw_adc_sum = 0;
    int raw_adc_val;

    // 采集多个样本进行平均，以降低噪声并提高有效分辨率 (过采样)
    for (int i = 0; i < ADC_READ_LEN; i++) {
        ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, ADC_CHANNEL, &raw_adc_val));
        raw_adc_sum += raw_adc_val;
        // 此处可根据需要添加微小延迟，以降低采样率或避免干扰
        // vTaskDelay(pdMS_TO_TICKS(1));
    }
    int raw_adc_avg = raw_adc_sum / ADC_READ_LEN;

    // 将ADC原始值转换为电压 (毫伏)
    int voltage_mv;
    if (adc_cali_handle) {
        // 使用校准后的转换
        ESP_ERROR_CHECK(adc_cali_raw_to_voltage(adc_cali_handle, raw_adc_avg, &voltage_mv));
    } else {
        // 粗略转换：原始值 -> 电压 (仅在无校准时使用，精度差)
        voltage_mv = raw_adc_avg * ADC_REF_VOLTAGE_MV / ((1 << ADC_BITWIDTH) - 1);
    }

    // 计算电流
    // 步骤：1. 计算经过放大后的传感器输出电压变化量 (伏特)
    //       2. 根据传感器灵敏度反推实际电流
    float voltage_change_v = (float)(voltage_mv - s_zero_voltage_mv) / 1000.0f;
    float current_a = voltage_change_v / (AMPLIFIER_GAIN * SENSOR_SENSITIVITY_V_PER_A);
    float current_ma = current_a * 1000.0f; // 转换为毫安

    // (调试用) 打印中间值
    // ESP_LOGI(TAG, "Raw:%d, V:%dmV, dV:%.3fV, I:%.3fmA", raw_adc_avg, voltage_mv, voltage_change_v, current_ma);

    return current_ma;
}

/**
 * @brief 主任务
 */
void app_main(void) {
    // 初始化串口 (用于printf输出)
    const uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &uart_config));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0));

    ESP_LOGI(TAG, "ESP32 高精度电流测量程序启动 (IDF v5.5)");

    // 初始化ADC
    adc_init();

    // 主循环：测量并打印电流值
    while (1) {
        float current_ma = measure_current_ma();
        printf("Current: %.2f mA\n", current_ma); // 通过串口输出，保留两位小数

        // 可根据需要调整测量间隔
        vTaskDelay(pdMS_TO_TICKS(500));
    }

    // 清理资源 (程序通常不会运行到这里)
    if (adc_cali_handle) {
        adc_cali_delete_scheme(adc_cali_handle);
    }
    if (adc1_handle) {
        adc_oneshot_del_unit(adc1_handle);
    }
}