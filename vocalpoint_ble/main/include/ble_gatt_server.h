/**************************************************************************************************/
/**
 * @file ble_gatt_server.h
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

#ifndef BLE_GATT_SERVER_H_
#define BLE_GATT_SERVER_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct ble_gatt_register_ctxt;

/**************************************************************************************************/
/**
 * @name ble_gatt_server_register_cb
 * @brief Handles NimBLE GATT registration events for logging and diagnostics.
 *
 * @param ctxt Registration context from NimBLE.
 * @param arg Optional user argument.
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void ble_gatt_server_register_cb(struct ble_gatt_register_ctxt *ctxt, void *arg);

/**************************************************************************************************/
/**
 * @name ble_gatt_server_init
 * @brief Initializes GAP/GATT services and registers the custom service table.
 *
 *
 *
 * @return int 0 on success, non-zero on error.
 */
/**************************************************************************************************/
int ble_gatt_server_init(void);

/**************************************************************************************************/
/**
 * @name ble_gatt_server_notify_battery
 * @brief Sends a battery notify to the active peer when subscribed.
 *
 * @param conn_handle Active BLE connection handle.
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void ble_gatt_server_notify_battery(uint16_t conn_handle);

/**************************************************************************************************/
/**
 * @name ble_gatt_server_set_battery
 * @brief Updates the internal battery cache used for notify payloads.
 *
 * @param pct Battery percentage.
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void ble_gatt_server_set_battery(uint8_t pct);

#ifdef __cplusplus
}
#endif

#endif
