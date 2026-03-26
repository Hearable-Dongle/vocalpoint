/**************************************************************************************************/
/**
 * @file ble_gatt_server.h
 * @brief BLE GATT server implementation for custom control and metadata characteristics.
 *
 * @version 0.1
 * @date 2026-03-03
 *
 * @copyright Copyright (c) 2026
 *
 */
/**************************************************************************************************/

#ifndef BLE_GATT_SERVER_H_
#define BLE_GATT_SERVER_H_

#ifdef __cplusplus
extern "C" {
#endif

/***************************************************************************************************
 * Function Declarations
 **************************************************************************************************/

/**************************************************************************************************/
/**
 * @name ble_gatt_server_init
 * @brief Initializes standard BLE services and registers custom service definitions.
 *
 * @return int 0 on success, non-zero NimBLE error code on failure.
 */
/**************************************************************************************************/
int ble_gatt_server_init(void);

#ifdef __cplusplus
}
#endif

#endif
