
#include "nvs_flash.h"
#include "esp_log.h"
#include "esp_bt.h"
#include "esp_bt_main.h"

void app_main(void) {
esp_log_level_set("*", ESP_LOG_INFO);
ESP_LOGI("MAIN", "Booting…");

esp_err_t ret = nvs_flash_init();

if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    ESP_ERROR_CHECK(nvs_flash_erase());
    ESP_ERROR_CHECK(nvs_flash_init());
}

ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT));
ESP_LOGI("MAIN", "Project skeleton running.");

}



