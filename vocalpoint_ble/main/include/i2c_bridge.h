/**************************************************************************************************/
/**
 * @file i2c_bridge.h
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

#ifndef I2C_BRIDGE_H_
#define I2C_BRIDGE_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**************************************************************************************************/
/**
 * @name i2c_bridge_init
 * @brief Initializes the I2C slave bridge and starts its background task.
 *
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void i2c_bridge_init(void);

/**************************************************************************************************/
/**
 * @name i2c_bridge_get_latest_volume
 * @brief Gets the latest volume value written by BLE and exposed to I2C master reads.
 *
 *
 *
 * @return int Latest volume percentage [0, 100].
 */
/**************************************************************************************************/
uint8_t i2c_bridge_get_latest_volume(void);

/**************************************************************************************************/
/**
 * @name i2c_bridge_set_latest_volume
 * @brief Updates the latest volume value shared with the I2C bridge.
 *
 * @param volume Volume percentage.
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void i2c_bridge_set_latest_volume(uint8_t volume);

/**************************************************************************************************/
/**
 * @name i2c_bridge_get_latest_battery
 * @brief Gets the latest battery value written by the I2C peer.
 *
 *
 *
 * @return int Latest battery percentage [0, 100].
 */
/**************************************************************************************************/
uint8_t i2c_bridge_get_latest_battery(void);

/**************************************************************************************************/
/**
 * @name i2c_bridge_set_latest_battery
 * @brief Updates the latest battery value shared with BLE.
 *
 * @param battery Battery percentage.
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void i2c_bridge_set_latest_battery(uint8_t battery);

#ifdef __cplusplus
}
#endif

#endif
