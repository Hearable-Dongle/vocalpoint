/**************************************************************************************************/
/**
 * @file main.h
 * @brief Application entrypoint declarations.
 *
 * @version 0.1
 * @date 2026-03-26
 *
 * @copyright Copyright (c) 2026
 *
 */
/**************************************************************************************************/

/***************************************************************************************************
 * Includes
 **************************************************************************************************/

// Third-party includes
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "nvs_flash.h"

// Project includes
#include "ble_manager.h"
#include "i2c.h"
#include "log.h"
#include "state.h"


/***************************************************************************************************
 * Function Declarations
 **************************************************************************************************/

/**************************************************************************************************/
/**
 * @name app_main
 * @brief Initializes NVS, application state, I2C, and BLE manager during firmware startup.
 *
 * @return void
 */
/**************************************************************************************************/
void app_main(void)
{
    // Define return code variable for error handling.
    esp_err_t err = ESP_OK;

    // Initialize NVS flash and handle any errors.
    err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND)
    {
        // Log the need for NVS flash erase and reinitialization.
        ESP_LOGI( 
            s_tag,
            "NVS flash initialization failed, erasing and reinitializing.\n"
            "\terror=%s\n",
            esp_err_to_name(err)
        );

        // Erase NVS flash, checking for errors.
        ESP_ERROR_CHECK(nvs_flash_erase());

        // Reinitialize NVS flash.
        err = nvs_flash_init();
    }

    // Check for errors in NVS flash initialization and log any failures.
    if (err != ESP_OK)
    {
        // Log an error if NVS flash initialization fails after erase and reinitialization attempts.
        ESP_LOGI(
            s_tag,
            "Failed to initialize NVS flash.\n"
            "\terror=%s\n",
            esp_err_to_name(err)
        );
    }
    else
    {
        // Log successful initialization of NVS flash.
        ESP_LOGI(
            s_tag,
            "NVS flash initialized successfully.\n"
        );
    }
    ESP_ERROR_CHECK(err);

    // Initialize application state.
    vp_state_init();

    // Initialize I2C communication.
    i2c_init();

    // Initialize BLE manager and handle any errors.
    err = ble_manager_init();
    if (err != ESP_OK) {
        // Log an error if BLE manager initialization fails.
        ESP_LOGI(
            s_tag,
            "Failed to initialize BLE manager"
            "error=%d",
            err
        );
    }
}
