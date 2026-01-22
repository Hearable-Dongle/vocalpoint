#include <string.h>
#include <stdio.h>
#include "esp_log.h"

static const char *TAG = "CMD";
extern void ble_srv_notify_evt(const uint8_t *data, size_t len);

static int is_ping(const uint8_t *buf, int len) {
    // naive check for {"cmd":"ping"}
    return (len >= 12 && memmem(buf, len, "\"ping\"", 6) != NULL);
}

void cmd_handle_write(const uint8_t *data, uint16_t len) {
    ESP_LOGI(TAG, "CMD RX: %.*s", len, (const char*)data);
    if (is_ping(data, len)) {
        const char *pong = "{\"evt\":\"pong\"}";
        ble_srv_notify_evt((const uint8_t*)pong, strlen(pong));
    }
    // extend: scan_start/connect/etc.
}
