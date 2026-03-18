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
 *   bit 3   VP_REQ_BAT    want current battery level
 *   bit 4   VP_REQ_ADDR   want current BLE address string
 *   bit 5   VP_REQ_P1     want current param1 string
 *   bit 6   VP_REQ_P2     want current param2 string
 *   bits 7-23 reserved, must be 0
 *   bits 24-31 VP_REQ_OFFSET  byte offset within the requested parameter payload
 *
 *   Special case: request == 0x00000000 → read status register only.
 *
 * Status register (ESP32 → RPi, 4 bytes little-endian uint32_t)
 * --------------------------------------------------------------
 *   bit 0   VP_FLAG_CHANGED  1 = at least one field has changed since last fetch
 *   bit 1   reserved (always 0)
 *   bit 2   VP_FLAG_VOL      volume changed
 *   bit 3   VP_FLAG_BAT      battery changed
 *   bit 4   VP_FLAG_ADDR     BLE address changed
 *   bit 5   VP_FLAG_P1       param1 changed
 *   bit 6   VP_FLAG_P2       param2 changed
 *   bits 7-31  reserved / future error flags
 *
 * Param response (ESP32 → RPi, chunked mailbox read)
 * ---------------------------------------------
 *   [0..3]  uint32_t response flags (little-endian), echoing the request
 *             including VP_REQ_DATA, param bit, and VP_REQ_OFFSET
 *   [4..N]  raw parameter data chunk
 *
 *   Volume / battery:  1 byte  (uint8_t, 0-100)
 *   BLE address:      40 bytes (null-padded UTF-8 string)
 *   Param1 / param2:  32 bytes (null-padded UTF-8 string)
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
#define VP_FLAG_CHANGED    (1U << 0)
#define VP_FLAG_VOL        (1U << 2)
#define VP_FLAG_BAT        (1U << 3)
#define VP_FLAG_ADDR       (1U << 4)
#define VP_FLAG_P1         (1U << 5)
#define VP_FLAG_P2         (1U << 6)

/* Request register bits (RPi → ESP32) */
#define VP_REQ_DATA        (1U << 1)
#define VP_REQ_VOL         (1U << 2)
#define VP_REQ_BAT         (1U << 3)
#define VP_REQ_ADDR        (1U << 4)
#define VP_REQ_P1          (1U << 5)
#define VP_REQ_P2          (1U << 6)
#define VP_REQ_OFFSET_SHIFT 24U
#define VP_REQ_OFFSET_MASK (0xFFU << VP_REQ_OFFSET_SHIFT)

/* Mask covering all per-parameter bits (same positions in both registers). */
#define VP_PARAM_BITS_MASK (VP_FLAG_VOL | VP_FLAG_BAT | VP_FLAG_ADDR | VP_FLAG_P1 | VP_FLAG_P2)

/* Payload sizes */
#define VP_PAYLOAD_VOL_LEN   1U
#define VP_PAYLOAD_BAT_LEN   1U
#define VP_PAYLOAD_ADDR_LEN  40U
#define VP_PAYLOAD_P1_LEN    32U
#define VP_PAYLOAD_P2_LEN    32U

/* Wire sizes */
#define VP_STATUS_LEN      4U   /* Status or request register is always 4 bytes */
#define VP_RESP_HDR_LEN    4U   /* Response header (flags) prefix on param replies */

/* Logical response lengths including the 4-byte header */
#define VP_RESP_VOL_LEN    (VP_RESP_HDR_LEN + VP_PAYLOAD_VOL_LEN)
#define VP_RESP_BAT_LEN    (VP_RESP_HDR_LEN + VP_PAYLOAD_BAT_LEN)
#define VP_RESP_ADDR_LEN   (VP_RESP_HDR_LEN + VP_PAYLOAD_ADDR_LEN)
#define VP_RESP_P1_LEN     (VP_RESP_HDR_LEN + VP_PAYLOAD_P1_LEN)
#define VP_RESP_P2_LEN     (VP_RESP_HDR_LEN + VP_PAYLOAD_P2_LEN)

/* Mailbox / chunk transport sizes */
#define VP_I2C_RAM_LEN        SOC_I2C_FIFO_LEN
#define VP_REQ_MAILBOX_OFFSET 0U
#define VP_REQ_MAILBOX_LEN    VP_STATUS_LEN
#define VP_RESP_MAILBOX_OFFSET VP_REQ_MAILBOX_LEN
#define VP_RESP_MAILBOX_LEN   (VP_I2C_RAM_LEN - VP_RESP_MAILBOX_OFFSET)
#define VP_RESP_PAYLOAD_MAX   (VP_RESP_MAILBOX_LEN - VP_RESP_HDR_LEN)

/* Minimum settle time the RPi must wait between writing a request and reading
 * the response.  This gives the ESP32 time to process the request and load its
 * TX buffer.  Value is in milliseconds. */
#define VP_SETTLE_MS       20U

#ifdef __cplusplus
}
#endif

#endif // I2C_PROTOCOL_H_
