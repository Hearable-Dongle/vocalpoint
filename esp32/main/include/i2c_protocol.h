/**************************************************************************************************/
/**
 * @file i2c_protocol.h
 * @brief VocalPoint ESP32 ↔ RPi I2C request/response protocol definitions.
 *
 * Protocol overview
 * -----------------
 * All communication is master-initiated (RPi is master, ESP32 is slave).
 * The RPi writes a 4-byte request into the ESP32's I2C RAM mailbox, waits
 * VP_SETTLE_MS, then reads the current response mailbox contents. There is no
 * queued TX FIFO in this protocol: each new request overwrites the single
 * current response.
 *
 * Request register (RPi → ESP32, 4 bytes little-endian uint32_t)
 * ---------------------------------------------------------------
 *   bit 0   always 0 from the RPi  (reserved for future ACK use)
 *   bit 1   VP_REQ_DATA   set to 1 when requesting a parameter value
 *   bit 2   VP_REQ_VOL    want current volume
 *   bit 3   VP_REQ_VOICE_PROFILE_NUM  want current voice profile number
 *   bit 4   VP_REQ_BLE_UUID_ADDR      want current BLE UUID/address string
 *   bit 5   VP_REQ_AUDIO_OUT_NAME     want current audio output device name string
 *   bit 6   VP_REQ_WIFI_SSID          want current Wi-Fi SSID string
 *   bit 7   VP_REQ_WIFI_PWD           want current Wi-Fi password string
 *   bit 8   VP_REQ_WRITE  set to 1 when issuing a write command
 *   bit 9   VP_REQ_WRITE_VOICE_PROFILE  payload mailbox contains a voice profile name
 *   bits 10-23 reserved, must be 0
 *   bits 24-31 VP_REQ_OFFSET  byte offset within the requested parameter payload
 *
 *   Special case: request == 0x00000000 → read status register only.
 *
 * Status register (ESP32 → RPi, 4 bytes little-endian uint32_t)
 * --------------------------------------------------------------
 *   bit 0   VP_FLAG_CHANGED  1 = at least one field has changed since last fetch
 *   bit 1   reserved (always 0)
 *   bit 2   VP_FLAG_VOL      volume changed
 *   bit 3   VP_FLAG_VOICE_PROFILE_NUM  voice profile number changed
 *   bit 4   VP_FLAG_BLE_UUID_ADDR      BLE UUID/address changed
 *   bit 5   VP_FLAG_AUDIO_OUT_NAME     audio output device name changed
 *   bit 6   VP_FLAG_WIFI_SSID          Wi-Fi SSID changed
 *   bit 7   VP_FLAG_WIFI_PWD           Wi-Fi password changed
 *   bits 8-31  reserved / future error flags
 *
 * Param response (ESP32 → RPi, chunked mailbox read)
 * ---------------------------------------------
 *   [0..3]  uint32_t response flags (little-endian), echoing the request
 *             including VP_REQ_DATA, param bit, and VP_REQ_OFFSET
 *   [4..N]  raw parameter data chunk
 *
 *   Volume / voice_profile_num: 1 byte  (uint8_t, 0-100)
 *   BLE UUID/address:          40 bytes (null-padded UTF-8 string)
 *   Audio output / Wi-Fi fields: 32 bytes (null-padded UTF-8 string)
 *
 * Mailbox layout (ESP32-C3 I2C RAM is 32 bytes total)
 * ----------------------------------------------------
 *   offset 0x00..0x03  request mailbox   (4-byte request register)
 *   offset 0x04..0x1F  response mailbox  (28 bytes total)
 *
 * The response mailbox therefore carries at most 24 payload bytes per read:
 *   4-byte header + up to 24 bytes payload = 28 bytes
 *
 * Long strings are fetched in multiple chunks by varying VP_REQ_OFFSET.
 *
 * Test write path
 * ---------------
 * To write a voice profile name from the RPi:
 *   1. Master writes a null-padded UTF-8 payload into mailbox offset 0x04.
 *   2. Master writes a 32-bit request word with VP_REQ_WRITE and
 *      VP_REQ_WRITE_VOICE_PROFILE set in the request mailbox at offset 0x00.
 *   3. ESP32 copies the payload into shared state and exposes it over BLE
 *      metadata as VOICE_PROFILE_NAME=<name>;VOICE_PROFILE_NAME_NUM=<n>.
 *
 * @version 0.1
 * @date 2026-03-18
 *
 * @copyright Copyright (c) 2026
 *
 */
/**************************************************************************************************/

#ifndef I2C_PROTOCOL_H_
#define I2C_PROTOCOL_H_

#ifdef __cplusplus
extern "C" {
#endif

#include "soc/soc_caps.h"

/* Status register bits (ESP32 → RPi) */
#define VP_FLAG_CHANGED             (1U << 0)
#define VP_FLAG_VOL                 (1U << 2)
#define VP_FLAG_VOICE_PROFILE_NUM   (1U << 3)
#define VP_FLAG_BLE_UUID_ADDR       (1U << 4)
#define VP_FLAG_AUDIO_OUT_NAME      (1U << 5)
#define VP_FLAG_WIFI_SSID           (1U << 6)
#define VP_FLAG_WIFI_PWD            (1U << 7)

/* Request register bits (RPi → ESP32) */
#define VP_REQ_DATA                 (1U << 1)
#define VP_REQ_VOL                  (1U << 2)
#define VP_REQ_VOICE_PROFILE_NUM    (1U << 3)
#define VP_REQ_BLE_UUID_ADDR        (1U << 4)
#define VP_REQ_AUDIO_OUT_NAME       (1U << 5)
#define VP_REQ_WIFI_SSID            (1U << 6)
#define VP_REQ_WIFI_PWD             (1U << 7)
#define VP_REQ_WRITE                (1U << 8)
#define VP_REQ_WRITE_VOICE_PROFILE  (1U << 9)
#define VP_REQ_OFFSET_SHIFT         24U
#define VP_REQ_OFFSET_MASK          (0xFFU << VP_REQ_OFFSET_SHIFT)

/* Mask covering all per-parameter bits (same positions in both registers). */
#define VP_PARAM_BITS_MASK (VP_FLAG_VOL | VP_FLAG_VOICE_PROFILE_NUM | VP_FLAG_BLE_UUID_ADDR | \
                            VP_FLAG_AUDIO_OUT_NAME | VP_FLAG_WIFI_SSID | VP_FLAG_WIFI_PWD)

/* Payload sizes */
#define VP_PAYLOAD_VOL_LEN              1U
#define VP_PAYLOAD_VOICE_PROFILE_NUM_LEN 1U
#define VP_PAYLOAD_BLE_UUID_ADDR_LEN    40U
#define VP_PAYLOAD_AUDIO_OUT_NAME_LEN   32U
#define VP_PAYLOAD_WIFI_SSID_LEN        32U
#define VP_PAYLOAD_WIFI_PWD_LEN         32U

/* Wire sizes */
#define VP_STATUS_LEN      4U   /* Status or request register is always 4 bytes */
#define VP_RESP_HDR_LEN    4U   /* Response header (flags) prefix on param replies */

/* Logical response lengths including the 4-byte header */
#define VP_RESP_VOL_LEN             (VP_RESP_HDR_LEN + VP_PAYLOAD_VOL_LEN)
#define VP_RESP_VOICE_PROFILE_NUM_LEN (VP_RESP_HDR_LEN + VP_PAYLOAD_VOICE_PROFILE_NUM_LEN)
#define VP_RESP_BLE_UUID_ADDR_LEN   (VP_RESP_HDR_LEN + VP_PAYLOAD_BLE_UUID_ADDR_LEN)
#define VP_RESP_AUDIO_OUT_NAME_LEN  (VP_RESP_HDR_LEN + VP_PAYLOAD_AUDIO_OUT_NAME_LEN)
#define VP_RESP_WIFI_SSID_LEN       (VP_RESP_HDR_LEN + VP_PAYLOAD_WIFI_SSID_LEN)
#define VP_RESP_WIFI_PWD_LEN        (VP_RESP_HDR_LEN + VP_PAYLOAD_WIFI_PWD_LEN)

/* Mailbox / chunk transport sizes */
#define VP_I2C_RAM_LEN          SOC_I2C_FIFO_LEN
#define VP_REQ_MAILBOX_OFFSET   0U
#define VP_REQ_MAILBOX_LEN      VP_STATUS_LEN
#define VP_RESP_MAILBOX_OFFSET  VP_REQ_MAILBOX_LEN
#define VP_RESP_MAILBOX_LEN     (VP_I2C_RAM_LEN - VP_RESP_MAILBOX_OFFSET)
#define VP_RESP_PAYLOAD_MAX     (VP_RESP_MAILBOX_LEN - VP_RESP_HDR_LEN)
#define VP_WRITE_MAILBOX_OFFSET VP_RESP_MAILBOX_OFFSET
#define VP_WRITE_MAILBOX_LEN    VP_RESP_MAILBOX_LEN

/* Minimum settle time the RPi must wait between writing a request and reading
 * the response.  This gives the ESP32 time to process the request and load its
 * TX buffer.  Value is in milliseconds. */
#define VP_SETTLE_MS       20U

#ifdef __cplusplus
}
#endif

#endif // I2C_PROTOCOL_H_
