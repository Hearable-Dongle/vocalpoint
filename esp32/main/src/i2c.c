/**************************************************************************************************/
/**
 * @file i2c.c
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

#include "i2c.h"

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
#include "state.h"

#define I2C_PORT                I2C_NUM_0
#define VP_I2C_SLAVE_ADDR       0x42
#define I2C_SDA_PIN             6
#define I2C_SCL_PIN             7
#define I2C_SEND_BUF_DEPTH      32
#define I2C_TASK_PRIORITY       1
#define I2C_TASK_PERIOD_MS      10

static const char *TAG = "i2c";
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

static int i2c_req_is_status_request(uint32_t req_flags)
{
    return req_flags == 0U;
}

static int i2c_req_is_param_request(uint32_t req_flags)
{
    uint32_t param_bits = req_flags & VP_PARAM_BITS_MASK;
    uint32_t unknown_bits = req_flags & ~(VP_REQ_DATA | VP_PARAM_BITS_MASK | VP_REQ_OFFSET_MASK);

    if ((req_flags & VP_REQ_DATA) == 0U) {
        return 0;
    }

    if (unknown_bits != 0U) {
        return 0;
    }

    if (param_bits == 0U || (param_bits & (param_bits - 1U)) != 0U) {
        return 0;
    }

    return 1;
}

static int i2c_req_is_voice_profile_write_request(uint32_t req_flags)
{
    const uint32_t expected = VP_REQ_WRITE | VP_REQ_WRITE_VOICE_PROFILE;
    return req_flags == expected;
}

static int i2c_req_is_audio_out_name_write_request(uint32_t req_flags)
{
    const uint32_t expected = VP_REQ_WRITE | VP_REQ_AUDIO_OUT_NAME;
    return req_flags == expected;
}

static esp_err_t i2c_mailbox_read_request(uint32_t *out_req)
{
    i2c_slave_dev_t *slave = (i2c_slave_dev_t *)s_i2c_slave;
    uint8_t req_buf[VP_REQ_MAILBOX_LEN];
    uint32_t rx_fifo_cnt = 0U;

    if (out_req == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    /* In RAM mode a true mailbox request from the Pi is a 5-byte write:
     *   [ram_offset=0x00][4-byte request word]
     * The subsequent transmit-receive used to read the response mailbox only
     * writes a single byte (0x04) to select the RAM offset. Ignore those
     * 1-byte selector writes so they cannot race with and replace a real
     * request before this task sees it. */
    i2c_ll_get_rxfifo_cnt(slave->base->hal.dev, &rx_fifo_cnt);
    if (rx_fifo_cnt < (VP_REQ_MAILBOX_LEN + 1U)) {
        return ESP_ERR_NOT_FOUND;
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

static esp_err_t i2c_mailbox_clear_request(void)
{
    uint8_t zero_req[VP_REQ_MAILBOX_LEN] = {0};
    return i2c_slave_write_ram(s_i2c_slave, VP_REQ_MAILBOX_OFFSET, zero_req, sizeof(zero_req));
}

static esp_err_t i2c_mailbox_read_write_payload(uint8_t *out, size_t len)
{
    i2c_slave_dev_t *slave = (i2c_slave_dev_t *)s_i2c_slave;

    if (out == NULL || len > VP_WRITE_MAILBOX_LEN) {
        return ESP_ERR_INVALID_ARG;
    }

    i2c_ll_read_by_nonfifo(slave->base->hal.dev,
                           VP_WRITE_MAILBOX_OFFSET,
                           out,
                           len);
    return ESP_OK;
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

    if (param_bit == VP_REQ_VOICE_PROFILE_NUM) {
        *payload = &snap->voice_profile_num;
        *clear_mask = VP_FLAG_VOICE_PROFILE_NUM;
        return VP_PAYLOAD_VOICE_PROFILE_NUM_LEN;
    }

    if (param_bit == VP_REQ_BLE_UUID_ADDR) {
        *payload = (const uint8_t *)snap->ble_uuid_addr;
        *clear_mask = VP_FLAG_BLE_UUID_ADDR;
        return VP_PAYLOAD_BLE_UUID_ADDR_LEN;
    }

    if (param_bit == VP_REQ_AUDIO_OUT_NAME) {
        *payload = (const uint8_t *)snap->audio_out_name_set;
        *clear_mask = VP_FLAG_AUDIO_OUT_NAME;
        return VP_PAYLOAD_AUDIO_OUT_NAME_LEN;
    }

    if (param_bit == VP_REQ_WIFI_SSID) {
        *payload = (const uint8_t *)snap->wifi_ssid;
        *clear_mask = VP_FLAG_WIFI_SSID;
        return VP_PAYLOAD_WIFI_SSID_LEN;
    }

    if (param_bit == VP_REQ_WIFI_PWD) {
        *payload = (const uint8_t *)snap->wifi_pwd;
        *clear_mask = VP_FLAG_WIFI_PWD;
        return VP_PAYLOAD_WIFI_PWD_LEN;
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
    if (i2c_req_is_status_request(req_flags)) {
        return i2c_render_status_response();
    }

    if (i2c_req_is_param_request(req_flags)) {
        return i2c_render_param_response(req_flags, snap);
    }

    return ESP_ERR_INVALID_ARG;
}

static esp_err_t i2c_handle_voice_profile_write(void)
{
    uint8_t payload[VP_WRITE_MAILBOX_LEN];
    char voice_name[VP_WRITE_MAILBOX_LEN + 1U];
    size_t copy_len = 0U;
    esp_err_t err;

    memset(payload, 0, sizeof(payload));
    err = i2c_mailbox_read_write_payload(payload, sizeof(payload));
    if (err != ESP_OK) {
        return err;
    }

    while (copy_len < sizeof(payload) && payload[copy_len] != '\0') {
        copy_len++;
    }

    memcpy(voice_name, payload, copy_len);
    voice_name[copy_len] = '\0';

    vp_state_register_voice_profile_name(voice_name);
    ESP_LOGI(TAG, "voice profile write received: '%s'", voice_name);

    err = i2c_render_status_response();
    if (err != ESP_OK) {
        return err;
    }

    return i2c_mailbox_clear_request();
}

static esp_err_t i2c_handle_audio_out_name_write(void)
{
    uint8_t payload[VP_WRITE_MAILBOX_LEN];
    char audio_out_name[VP_WRITE_MAILBOX_LEN + 1U];
    size_t copy_len = 0U;
    esp_err_t err;

    memset(payload, 0, sizeof(payload));
    err = i2c_mailbox_read_write_payload(payload, sizeof(payload));
    if (err != ESP_OK) {
        return err;
    }


    while (copy_len < sizeof(payload) && payload[copy_len] != '\0') {
        copy_len++;
    }

    memcpy(audio_out_name, payload, copy_len);
    audio_out_name[copy_len] = '\0';
    vp_state_announce_audio_out_name(audio_out_name);
    ESP_LOGI(TAG, "audio output announcement received: '%s'", audio_out_name);

    err = i2c_render_status_response();
    if (err != ESP_OK) {
        return err;
    }

    return i2c_mailbox_clear_request();
}

static void i2c_task(void *arg)
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

        if (i2c_req_is_voice_profile_write_request(req_flags)) {
            err = i2c_handle_voice_profile_write();
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "voice profile write failed: %s", esp_err_to_name(err));
            }
            vTaskDelay(pdMS_TO_TICKS(I2C_TASK_PERIOD_MS));
            continue;
        }

        if (i2c_req_is_audio_out_name_write_request(req_flags)) {
            err = i2c_handle_audio_out_name_write();
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "audio output write failed: %s", esp_err_to_name(err));
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
            } else if (err != ESP_ERR_INVALID_ARG) {
                ESP_LOGW(TAG, "response render failed: %s", esp_err_to_name(err));
            } else {
                /* Ignore transient malformed writes so the previous valid
                 * response remains in the mailbox for the master's follow-up read. */
            }
        }

        vTaskDelay(pdMS_TO_TICKS(I2C_TASK_PERIOD_MS));
    }
}

void i2c_init(void)
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

    xTaskCreate(i2c_task, "i2c_bridge", 4096, NULL, I2C_TASK_PRIORITY, NULL);
}
