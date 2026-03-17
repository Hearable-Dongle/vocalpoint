/**************************************************************************************************/
/**
 * @file ble_manager.h
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

#ifndef BLE_MANAGER_H_
#define BLE_MANAGER_H_

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**************************************************************************************************/
/**
 * @name ble_manager_init
 * @brief Initializes NimBLE host configuration, GATT server, and BLE host task.
 *
 *
 *
 * @return int ESP_OK on success, error code otherwise.
 */
/**************************************************************************************************/
esp_err_t ble_manager_init(void);

#ifdef __cplusplus
}
#endif

#endif
