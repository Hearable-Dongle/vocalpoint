/**************************************************************************************************/
/**
 * @file i2c_bridge.c
 * @brief VocalPoint I2C slave mailbox protocol.
 *
 * The ESP32-C3 uses the I2C controller's 32-byte internal RAM as two mailboxes:
 *   - request mailbox  at offset 0x00 (4 bytes)
 *   - response mailbox at offset 0x04 (28 bytes)
 *
 * The RPi writes a 32-bit request register into the request mailbox, waits
 * VP_SETTLE_MS, then reads the response mailbox. Unlike the FIFO slave API,
 * there is only one current response at a time, so stale replies are
 * overwritten instead of being queued indefinitely.
 *
 * @version 0.1
 * @date 2026-03-18
 *
 * @copyright Copyright (c) 2026
 */
/**************************************************************************************************/

#include "i2c_bridge.h"

#include <inttypes.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/i2c_slave.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "hal/i2c_ll.h"
#include "i2c_protocol.h"
#include "i2c_private.h"
#include "shared_state.h"

#define I2C_PORT                I2C_NUM_0
#define VP_I2C_SLAVE_ADDR       0x42
#define I2C_SDA_PIN             6
#define I2C_SCL_PIN             7
#define I2C_SEND_BUF_DEPTH      32
#define I2C_TASK_PRIORITY       1
#define I2C_TASK_PERIOD_MS      10

static const char *TAG = "i2c_bridge";
static i2c_slave_dev_handle_t s_i2c_slave;

typedef struct {
    uint32_t request;
    uint32_t state_tag;
} i2c_render_key_t;

static void put_u32_le(uint8_t *buf, uint32_t val)
{
    buf[0] = (uint8_t)(val & 0xFFU);
    buf[1] = (uint8_t)((val >> 8) & 0xFFU);
    buf[2] = (uint8_t)((val >> 16) & 0xFFU);
    buf[3] = (uint8_t)((val >> 24) & 0xFFU);
}

static uint32_t get_u32_le(const uint8_t *buf)
{
    return (uint32_t)buf[0]
         | ((uint32_t)buf[1] << 8)
         | ((uint32_t)buf[2] << 16)
         | ((uint32_t)buf[3] << 24);
}

static uint32_t vp_req_get_offset(uint32_t req_flags)
{
    return (req_flags & VP_REQ_OFFSET_MASK) >> VP_REQ_OFFSET_SHIFT;
}

static uint32_t vp_state_get_render_tag(uint32_t req_flags, const vp_state_snapshot_t *snap)
{
    if ((req_flags & VP_REQ_DATA) != 0U) {
        return snap->seq;
    }

    return vp_state_get_dirty_flags();
}

static esp_err_t i2c_mailbox_read_request(uint32_t *out_req)
{
    i2c_slave_dev_t *slave = (i2c_slave_dev_t *)s_i2c_slave;
    uint8_t req_buf[VP_REQ_MAILBOX_LEN];

    if (out_req == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Read directly from the I2C RAM without a critical section.
     * In access_ram_en mode the hardware updates RAM[0..3] atomically when the
     * master completes its write transaction.  The 20 ms RPi settle time plus
     * the master's header-echo retry loop make a torn 4-byte read harmless. */
    i2c_ll_read_by_nonfifo(slave->base->hal.dev,
                           VP_REQ_MAILBOX_OFFSET,
                           req_buf,
                           VP_REQ_MAILBOX_LEN);

    *out_req = get_u32_le(req_buf);
    return ESP_OK;
}

static esp_err_t i2c_mailbox_write_response(const uint8_t *resp, size_t len)
{
    uint8_t mailbox[VP_RESP_MAILBOX_LEN];

    if (resp == NULL || len > sizeof(mailbox)) {
        return ESP_ERR_INVALID_ARG;
    }

    memset(mailbox, 0, sizeof(mailbox));
    memcpy(mailbox, resp, len);
    return i2c_slave_write_ram(s_i2c_slave, VP_RESP_MAILBOX_OFFSET, mailbox, sizeof(mailbox));
}

static size_t vp_param_payload_info(uint32_t param_bit,
                                    const vp_state_snapshot_t *snap,
                                    const uint8_t **payload,
                                    uint32_t *clear_mask)
{
    if (payload == NULL || clear_mask == NULL || snap == NULL) {
        return 0U;
    }

    if (param_bit == VP_REQ_VOL) {
        *payload = &snap->volume;
        *clear_mask = VP_FLAG_VOL;
        return VP_PAYLOAD_VOL_LEN;
    }

    if (param_bit == VP_REQ_BAT) {
        *payload = &snap->battery;
        *clear_mask = VP_FLAG_BAT;
        return VP_PAYLOAD_BAT_LEN;
    }

    if (param_bit == VP_REQ_ADDR) {
        *payload = (const uint8_t *)snap->ble_addr;
        *clear_mask = VP_FLAG_ADDR;
        return VP_PAYLOAD_ADDR_LEN;
    }

    if (param_bit == VP_REQ_P1) {
        *payload = (const uint8_t *)snap->param1;
        *clear_mask = VP_FLAG_P1;
        return VP_PAYLOAD_P1_LEN;
    }

    if (param_bit == VP_REQ_P2) {
        *payload = (const uint8_t *)snap->param2;
        *clear_mask = VP_FLAG_P2;
        return VP_PAYLOAD_P2_LEN;
    }

    *payload = NULL;
    *clear_mask = 0U;
    return 0U;
}

static esp_err_t i2c_render_status_response(void)
{
    uint8_t resp[VP_STATUS_LEN];
    uint32_t flags = vp_state_get_dirty_flags();

    put_u32_le(resp, flags);
    return i2c_mailbox_write_response(resp, sizeof(resp));
}

static esp_err_t i2c_render_param_response(uint32_t req_flags, const vp_state_snapshot_t *snap)
{
    uint32_t param_bit = req_flags & VP_PARAM_BITS_MASK;
    uint32_t req_offset = vp_req_get_offset(req_flags);
    uint8_t resp[VP_RESP_MAILBOX_LEN];
    const uint8_t *payload = NULL;
    uint32_t clear_mask = 0U;
    size_t payload_total;
    size_t chunk_len = 0U;

    memset(resp, 0, sizeof(resp));

    if (param_bit == 0U || (param_bit & (param_bit - 1U)) != 0U) {
        ESP_LOGW(TAG, "invalid param request 0x%08" PRIx32, req_flags);
        return i2c_mailbox_write_response(resp, 0U);
    }

    payload_total = vp_param_payload_info(param_bit, snap, &payload, &clear_mask);
    if (payload_total == 0U || payload == NULL) {
        ESP_LOGW(TAG, "unsupported param request 0x%08" PRIx32, req_flags);
        return i2c_mailbox_write_response(resp, 0U);
    }
    put_u32_le(resp, req_flags);

    if (req_offset < payload_total) {
        chunk_len = payload_total - req_offset;
        if (chunk_len > VP_RESP_PAYLOAD_MAX) {
            chunk_len = VP_RESP_PAYLOAD_MAX;
        }
        memcpy(&resp[VP_RESP_HDR_LEN], payload + req_offset, chunk_len);
    } else {
        ESP_LOGW(TAG,
                 "request offset out of range: req=0x%08" PRIx32 " total=%u",
                 req_flags,
                 (unsigned)payload_total);
    }

    esp_err_t err = i2c_mailbox_write_response(resp, sizeof(resp));
    if (err != ESP_OK) {
        return err;
    }

    if (chunk_len != 0U && (req_offset + chunk_len) >= payload_total) {
        vp_state_clear_dirty_bits(clear_mask);
    }

    return ESP_OK;
}

static esp_err_t i2c_render_response(uint32_t req_flags, const vp_state_snapshot_t *snap)
{
    uint32_t unknown_bits = req_flags & ~(VP_REQ_DATA | VP_PARAM_BITS_MASK | VP_REQ_OFFSET_MASK);
    if (unknown_bits != 0U) {
        ESP_LOGW(TAG, "request has unknown bits set: req=0x%08" PRIx32, req_flags);
    }

    if ((req_flags & VP_REQ_DATA) != 0U) {
        return i2c_render_param_response(req_flags, snap);
    }

    return i2c_render_status_response();
}

static void i2c_bridge_task(void *arg)
{
    (void)arg;

    i2c_render_key_t last_key = {
        .request = UINT32_MAX,
        .state_tag = UINT32_MAX,
    };

    while (1) {
        uint32_t req_flags = 0U;
        vp_state_snapshot_t snap;

        esp_err_t err = i2c_mailbox_read_request(&req_flags);
        if (err != ESP_OK) {
            if (err != ESP_ERR_NOT_FOUND) {
                ESP_LOGW(TAG, "request mailbox read failed: %s", esp_err_to_name(err));
            }
            vTaskDelay(pdMS_TO_TICKS(I2C_TASK_PERIOD_MS));
            continue;
        }

        vp_state_get_snapshot(&snap);
        i2c_render_key_t next_key = {
            .request = req_flags,
            .state_tag = vp_state_get_render_tag(req_flags, &snap),
        };

        if (next_key.request != last_key.request || next_key.state_tag != last_key.state_tag) {
            err = i2c_render_response(req_flags, &snap);
            if (err == ESP_OK) {
                last_key = next_key;
            } else {
                ESP_LOGW(TAG, "response render failed: %s", esp_err_to_name(err));
            }
        }

        vTaskDelay(pdMS_TO_TICKS(I2C_TASK_PERIOD_MS));
    }
}

void i2c_bridge_init(void)
{
    i2c_slave_config_t conf = {
        .i2c_port = I2C_PORT,
        .sda_io_num = I2C_SDA_PIN,
        .scl_io_num = I2C_SCL_PIN,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        /* ESP-IDF still validates and allocates this even in access_ram_en mode. */
        .send_buf_depth = I2C_SEND_BUF_DEPTH,
        .slave_addr = VP_I2C_SLAVE_ADDR,
        .addr_bit_len = I2C_ADDR_BIT_LEN_7,
        .intr_priority = 0,
        .flags.access_ram_en = true,
    };
    uint8_t init_ram[VP_I2C_RAM_LEN];

    ESP_ERROR_CHECK(gpio_set_pull_mode(I2C_SDA_PIN, GPIO_PULLUP_ONLY));
    ESP_ERROR_CHECK(gpio_set_pull_mode(I2C_SCL_PIN, GPIO_PULLUP_ONLY));

    ESP_ERROR_CHECK(i2c_new_slave_device(&conf, &s_i2c_slave));

    memset(init_ram, 0, sizeof(init_ram));
    ESP_ERROR_CHECK(i2c_slave_write_ram(s_i2c_slave, 0U, init_ram, sizeof(init_ram)));

    ESP_LOGI(TAG,
             "I2C slave ready  port=%d addr=0x%02X sda=%d scl=%d mode=mailbox req_off=%u resp_off=%u",
             I2C_PORT,
             VP_I2C_SLAVE_ADDR,
             I2C_SDA_PIN,
             I2C_SCL_PIN,
             (unsigned)VP_REQ_MAILBOX_OFFSET,
             (unsigned)VP_RESP_MAILBOX_OFFSET);

    xTaskCreate(i2c_bridge_task, "i2c_bridge", 4096, NULL, I2C_TASK_PRIORITY, NULL);
}
