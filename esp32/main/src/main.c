/**************************************************************************************************/
/**
 * @file main.c
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

#include "ble_manager.h"
#include "i2c.h"
#include "state.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "nvs_flash.h"

static const char *s_tag = "app_main";

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    vp_state_init();
    i2c_init();

    err = ble_manager_init();
    if (err != ESP_OK) {
        ESP_LOGE(s_tag, "BLE manager init failed: %d", err);
    }
}
