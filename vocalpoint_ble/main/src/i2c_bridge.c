/**************************************************************************************************/
/**
 * @file i2c_bridge.c
 * @author
 * @brief
 *
 * @version 0.1
 * @date 2026-03-03
 *
 * @copyright Copyright (c) 2026
 *
 */
/**************************************************************************************************/

#include "i2c_bridge.h"
#include "driver/i2c.h"
#include "esp_err.h"

#define I2C_PORT I2C_NUM_0
#define I2C_SLAVE_ADDR 0x42
#define I2C_SDA_PIN 4
#define I2C_SCL_PIN 5

static volatile uint8_t s_latest_volume = 50;
static volatile uint8_t s_latest_battery = 87;

static void i2c_bridge_task(void *arg)
{
    (void)arg;

    while (1) {
        // If Pi reads, return the latest volume set by BLE.
        uint8_t tx = s_latest_volume;
        i2c_slave_write_buffer(I2C_PORT, &tx, 1, 10 / portTICK_PERIOD_MS);

        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

void i2c_bridge_init(void)
{
    i2c_config_t conf = {
        .mode = I2C_MODE_SLAVE,
        .sda_io_num = I2C_SDA_PIN,
        .scl_io_num = I2C_SCL_PIN,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .slave = {
            .addr_10bit_en = 0,
            .slave_addr = I2C_SLAVE_ADDR,
        },
    };

    ESP_ERROR_CHECK(i2c_param_config(I2C_PORT, &conf));
    ESP_ERROR_CHECK(i2c_driver_install(I2C_PORT, conf.mode, 256, 256, 0));

    xTaskCreate(i2c_bridge_task, "i2c_bridge", 2048, NULL, 5, NULL);
}

uint8_t i2c_bridge_get_latest_volume(void)
{
    return s_latest_volume;
}

void i2c_bridge_set_latest_volume(uint8_t volume)
{
    if (volume > 100) {
        volume = 100;
    }

    s_latest_volume = volume;
}

uint8_t i2c_bridge_get_latest_battery(void)
{
    return s_latest_battery;
}

void i2c_bridge_set_latest_battery(uint8_t battery)
{
    if (battery > 100) {
        battery = 100;
    }

    s_latest_battery = battery;
}
