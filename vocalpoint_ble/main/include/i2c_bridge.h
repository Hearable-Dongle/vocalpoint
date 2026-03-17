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

#ifdef __cplusplus
}
#endif

#endif
