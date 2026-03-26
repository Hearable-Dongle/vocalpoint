/**************************************************************************************************/
/**
 * @file ble_manager.h
 * @brief BLE manager module for GAP event handling, advertisement management, and connection
 *        lifecycle.
 *
 * @version 0.1
 * @date 2026-03-03
 *
 * @copyright Copyright (c) 2026
 *
 */
/**************************************************************************************************/

#ifndef BLE_MANAGER_H_
#define BLE_MANAGER_H_

#ifdef __cplusplus
extern "C" {
#endif

/***************************************************************************************************
 * Includes
 **************************************************************************************************/

// Third-party includes
#include "esp_err.h"


/***************************************************************************************************
 * Macro Declarations
 **************************************************************************************************/

/**************************************************************************************************/
/**
 * @name BLE_ADV_SERVICE_UUID
 * @brief UUID for the BLE advertisement service.
 */
/**************************************************************************************************/
#define BLE_ADV_SERVICE_UUID 0x1811


/***************************************************************************************************
 * Function Declarations
 **************************************************************************************************/

/**************************************************************************************************/
/**
 * @name ble_store_config_init
 * @brief Initializes the NimBLE persistent storage configuration for bonding and security data.
 *
 * @return void
 */
/**************************************************************************************************/
extern void ble_store_config_init(void);

/**************************************************************************************************/
/**
 * @name ble_manager_init
 * @brief Initializes NimBLE host configuration, GATT server, and BLE host task.
 *
 * @return int ESP_OK on success, error code otherwise.
 */
/**************************************************************************************************/
esp_err_t ble_manager_init(void);

#ifdef __cplusplus
}
#endif

#endif
