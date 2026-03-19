/**************************************************************************************************/
/**
 * @file state.h
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

#ifndef STATE_H_
#define STATE_H_

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define VP_MAGIC_BIT_LEN                  1
#define VP_FRAME_VERSION_LEN              1
#define VP_SEQ_MAX_LEN                    4
#define VP_VOLUME_LEN                     1
#define VP_VOICE_PROFILE_NUM_LEN          1
#define VP_BLE_ADDR_MAX_LEN               40
#define VP_PARAM_MAX_LEN                  32
#define VP_VOICE_PROFILE_NAME_NUM_LEN     1
#define VP_VOICE_PROFILE_NAME_MAX_LEN     28
#define VP_MAX_VOICE_PROFILES             16
#define VP_CRC16_LEN                      2

#define VP_FRAME_MAGIC          0xA5
#define VP_FRAME_VERSION        0x01

// Current total size is 205 bytes before CRC, 207 bytes including CRC.
#define VP_I2C_FRAME_SIZE (VP_MAGIC_BIT_LEN + VP_FRAME_VERSION_LEN + VP_SEQ_MAX_LEN + VP_VOLUME_LEN + \
                           VP_VOICE_PROFILE_NUM_LEN + VP_BLE_ADDR_MAX_LEN + VP_PARAM_MAX_LEN + \
                           VP_PARAM_MAX_LEN + VP_PARAM_MAX_LEN + VP_PARAM_MAX_LEN + \
                           VP_VOICE_PROFILE_NAME_NUM_LEN + VP_VOICE_PROFILE_NAME_MAX_LEN + \
                           VP_CRC16_LEN)

typedef struct {
    uint32_t seq;
    uint8_t volume;
    uint8_t voice_profile_num;
    char ble_uuid_addr[VP_BLE_ADDR_MAX_LEN];
    char audio_out_name_send[VP_PARAM_MAX_LEN];
    char audio_out_name_set[VP_PARAM_MAX_LEN];
    char wifi_ssid[VP_PARAM_MAX_LEN];
    char wifi_pwd[VP_PARAM_MAX_LEN];
    uint8_t voice_profile_name_num;
    char voice_profile_name[VP_VOICE_PROFILE_NAME_MAX_LEN];
} vp_state_snapshot_t;

void vp_state_init(void);

/**************************************************************************************************/
/**
 * @name vp_state_set_volume
 * @brief Updates the current volume field in shared state.
 *
 * @param volume Volume percentage [0, 100].
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_set_volume(uint8_t volume);

/**************************************************************************************************/
/**
 * @name vp_state_set_voice_profile_number
 * @brief Updates the selected voice profile number field in shared state.
 *
 * @param voice_profile_number Voice profile number [0, 100].
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_set_voice_profile_number(uint8_t voice_profile_number);

/**************************************************************************************************/
/**
 * @name vp_state_set_ble_uuid_addr
 * @brief Updates the BLE UUID/address string in shared state.
 *
 * This value is BLE metadata only. It is no longer part of the I2C dirty-bit
 * parameter map now that bit 4 is used for the reboot flag.
 *
 * @param addr Zero-terminated BLE address string.
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_set_ble_uuid_addr(const char *addr);

/**************************************************************************************************/
/**
 * @name vp_state_set_audio_out_name
 * @brief Updates the selected audio output device name string in shared state.
 *
 * @param value Zero-terminated string.
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_set_audio_out_name(const char *value);

/**************************************************************************************************/
/**
 * @name vp_state_announce_audio_out_name
 * @brief Stores the latest audio output device name announced by the RPi.
 *
 * This value is exposed over BLE so the mobile app can build a list of output
 * device names without using the phone-side scan path.
 *
 * @param value Zero-terminated string.
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_announce_audio_out_name(const char *value);

/**************************************************************************************************/
/**
 * @name vp_state_set_wifi_ssid
 * @brief Updates the Wi-Fi SSID string in shared state.
 *
 * @param value Zero-terminated string.
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_set_wifi_ssid(const char *value);

/**************************************************************************************************/
/**
 * @name vp_state_set_wifi_pwd
 * @brief Updates the Wi-Fi password string in shared state.
 *
 * @param value Zero-terminated string.
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_set_wifi_pwd(const char *value);

/**************************************************************************************************/
/**
 * @name vp_state_register_voice_profile_name
 * @brief Registers or refreshes a discovered voice profile name and its assigned number.
 *
 * @param value Zero-terminated string.
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_register_voice_profile_name(const char *value);

/**************************************************************************************************/
/**
 * @name vp_state_get_snapshot
 * @brief Copies the latest shared state into an output snapshot.
 *
 * @param out Output snapshot pointer.
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_get_snapshot(vp_state_snapshot_t *out);

/**************************************************************************************************/
/**
 * @name vp_state_build_i2c_frame
 * @brief Serializes shared state into the fixed I2C frame with CRC16.
 *
 * @param out Output byte buffer.
 * @param out_len Output buffer size.
 *
 * @return int Number of bytes written, or 0 on failure.
 */
/**************************************************************************************************/
size_t vp_state_build_i2c_frame(uint8_t *out, size_t out_len);

/**************************************************************************************************/
/**
 * @name vp_state_update_from_ble_payload
 * @brief Parses BLE payload tokens and updates mapped shared-state fields.
 *
 * @param payload Raw payload bytes.
 * @param payload_len Payload length.
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_update_from_ble_payload(const uint8_t *payload, uint16_t payload_len);

/**************************************************************************************************/
/**
 * @name vp_state_get_dirty_flags
 * @brief Returns the current 32-bit dirty-flag register without clearing it.
 *
 * Bit positions match the VP_FLAG_* constants in i2c_protocol.h.
 * VP_FLAG_CHANGED (bit 0) is set whenever any field has been updated.
 * Individual status bits reflect which fields/events have changed since the
 * last call to vp_state_clear_dirty_bits().
 *
 * @return uint32_t Current dirty flags.
 */
/**************************************************************************************************/
uint32_t vp_state_get_dirty_flags(void);

/**************************************************************************************************/
/**
 * @name vp_state_clear_dirty_bits
 * @brief Atomically clears the specified bits from the dirty-flag register.
 *
 * Called by i2c_bridge after the RPi has successfully fetched a parameter or
 * acknowledged a status bit such as VP_FLAG_REBOOT. If clearing the last
 * remaining dirty status bit also makes the status mask empty,
 * VP_FLAG_CHANGED is automatically cleared as well.
 *
 * @param mask  Bitmask of VP_FLAG_* bits to clear.
 */
/**************************************************************************************************/
void vp_state_clear_dirty_bits(uint32_t mask);

/**************************************************************************************************/
/**
 * @name vp_state_testing_tick
 * @brief Advances the dummy shared state once when I2C testing mode is enabled.
 *
 *
 *
 * @return int Not used.
 */
/**************************************************************************************************/
void vp_state_testing_tick(void);

#ifdef __cplusplus
}
#endif

#endif // STATE_H
