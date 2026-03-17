/**************************************************************************************************/
/**
 * @file i2c_bridge.c
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

#include "i2c_bridge.h"

#include <ctype.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/i2c_slave.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "shared_state.h"

#define I2C_PORT I2C_NUM_0
#define I2C_SLAVE_ADDR 0x42
#define I2C_SDA_PIN 6
#define I2C_SCL_PIN 7
#define I2C_RX_BUF_LEN 128
#define I2C_TX_BUF_DEPTH (VP_I2C_FRAME_SIZE * 4)
#define I2C_STREAM_PERIOD_MS 50

typedef struct {
    uint8_t data[I2C_RX_BUF_LEN];
} i2c_rx_item_t;

static const char *TAG = "i2c_bridge";
static i2c_slave_dev_handle_t s_i2c_slave;
static QueueHandle_t s_i2c_rx_queue;
static uint8_t s_i2c_rx_buffer[I2C_RX_BUF_LEN];

static void i2c_bridge_queue_snapshot(void)
{
    static uint32_t s_last_tx_seq = UINT32_MAX;

    uint8_t tx_frame[VP_I2C_FRAME_SIZE];
    size_t tx_len = vp_state_build_i2c_frame(tx_frame, sizeof(tx_frame));

    if (tx_len == 0U) {
        return;
    }

    uint32_t seq = (uint32_t)tx_frame[2]
                 | ((uint32_t)tx_frame[3] << 8)
                 | ((uint32_t)tx_frame[4] << 16)
                 | ((uint32_t)tx_frame[5] << 24);

    if (seq == s_last_tx_seq) {
        return;
    }

    esp_err_t err = i2c_slave_transmit(s_i2c_slave, tx_frame, (int)tx_len, 0);
    if (err == ESP_OK) {
        s_last_tx_seq = seq;
    } else if (err != ESP_ERR_TIMEOUT && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGW(TAG, "i2c_slave_transmit failed: %s", esp_err_to_name(err));
    }
}

static esp_err_t i2c_bridge_arm_receive(void)
{
    memset(s_i2c_rx_buffer, 0, sizeof(s_i2c_rx_buffer));
    return i2c_slave_receive(s_i2c_slave, s_i2c_rx_buffer, sizeof(s_i2c_rx_buffer));
}

static IRAM_ATTR bool i2c_bridge_rx_done_callback(i2c_slave_dev_handle_t channel,
                                                  const i2c_slave_rx_done_event_data_t *edata,
                                                  void *user_data)
{
    BaseType_t high_task_wakeup = pdFALSE;
    QueueHandle_t rx_queue = (QueueHandle_t)user_data;
    i2c_rx_item_t item;

    (void)channel;

    memcpy(item.data, edata->buffer, I2C_RX_BUF_LEN);
    xQueueSendFromISR(rx_queue, &item, &high_task_wakeup);
    return high_task_wakeup == pdTRUE;
}

static size_t i2c_command_length(const uint8_t *data, size_t max_len)
{
    if (data == NULL) {
        return 0U;
    }

    return strnlen((const char *)data, max_len);
}

static int i2c_command_is_poll(const uint8_t *data, size_t len)
{
    static const char *const poll_cmds[] = {"GET", "READ", "POLL"};
    char buffer[16];

    if (data == NULL || len == 0U) {
        return 0;
    }

    while (len > 0U && isspace((unsigned char)data[0])) {
        data++;
        len--;
    }

    while (len > 0U && isspace((unsigned char)data[len - 1U])) {
        len--;
    }

    if (len == 0U || len >= sizeof(buffer)) {
        return 0;
    }

    memcpy(buffer, data, len);
    buffer[len] = '\0';

    for (size_t i = 0; i < len; i++) {
        buffer[i] = (char)toupper((unsigned char)buffer[i]);
    }

    for (size_t i = 0; i < sizeof(poll_cmds) / sizeof(poll_cmds[0]); i++) {
        if (strcmp(buffer, poll_cmds[i]) == 0) {
            return 1;
        }
    }

    return 0;
}

static void i2c_bridge_task(void *arg)
{
    (void)arg;

    i2c_rx_item_t rx_item;

    i2c_bridge_queue_snapshot();
    ESP_ERROR_CHECK(i2c_bridge_arm_receive());

    while (1) {
        if (xQueueReceive(s_i2c_rx_queue, &rx_item, 0) == pdTRUE) {
            size_t rx_len = i2c_command_length(rx_item.data, sizeof(rx_item.data));
            if (rx_len > 0U && !i2c_command_is_poll(rx_item.data, rx_len)) {
                vp_state_update_from_ble_payload(rx_item.data, (uint16_t)rx_len);
            }
            ESP_ERROR_CHECK(i2c_bridge_arm_receive());
        }

        i2c_bridge_queue_snapshot();
        vTaskDelay(pdMS_TO_TICKS(I2C_STREAM_PERIOD_MS));
    }
}

void i2c_bridge_init(void)
{
    i2c_slave_config_t conf = {
        .i2c_port = I2C_PORT,
        .sda_io_num = I2C_SDA_PIN,
        .scl_io_num = I2C_SCL_PIN,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .send_buf_depth = I2C_TX_BUF_DEPTH,
        .slave_addr = I2C_SLAVE_ADDR,
        .addr_bit_len = I2C_ADDR_BIT_LEN_7,
        .intr_priority = 0,
    };
    i2c_slave_event_callbacks_t callbacks = {
        .on_recv_done = i2c_bridge_rx_done_callback,
    };

    ESP_ERROR_CHECK(gpio_set_pull_mode(I2C_SDA_PIN, GPIO_PULLUP_ONLY));
    ESP_ERROR_CHECK(gpio_set_pull_mode(I2C_SCL_PIN, GPIO_PULLUP_ONLY));

    s_i2c_rx_queue = xQueueCreate(4, sizeof(i2c_rx_item_t));
    ESP_ERROR_CHECK(s_i2c_rx_queue != NULL ? ESP_OK : ESP_ERR_NO_MEM);

    ESP_ERROR_CHECK(i2c_new_slave_device(&conf, &s_i2c_slave));
    ESP_ERROR_CHECK(i2c_slave_register_event_callbacks(s_i2c_slave, &callbacks, s_i2c_rx_queue));

    // A full slave TX ringbuffer is expected when no master is reading.
    esp_log_level_set("i2c.slave", ESP_LOG_NONE);

    ESP_LOGI(TAG,
             "I2C slave ready on port=%d addr=0x%02X sda=%d scl=%d mode=frame_stream",
             I2C_PORT,
             I2C_SLAVE_ADDR,
             I2C_SDA_PIN,
             I2C_SCL_PIN);

    xTaskCreate(i2c_bridge_task, "i2c_bridge", 4096, NULL, 1, NULL);
}
