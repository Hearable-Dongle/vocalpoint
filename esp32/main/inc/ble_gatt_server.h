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
 * @name ble_gatt_server_notify_voice_profile_number
 * @brief Sends the current voice profile number to the active peer when subscribed.
 *
 * @param conn_handle Active BLE connection handle.
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void ble_gatt_server_notify_voice_profile_number(uint16_t conn_handle);

/**************************************************************************************************/
/**
 * @name ble_gatt_server_set_voice_profile_number
 * @brief Updates the numerical representation of a voice profile.
 *
 * @param voice_profile_number Voice profile number.
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void ble_gatt_server_set_voice_profile_number(uint8_t voice_profile_number);

#ifdef __cplusplus
}
#endif

#endif
