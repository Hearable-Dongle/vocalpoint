#include <string.h>
#include "esp_timer.h"

extern void ble_srv_notify_sts(const uint8_t *data, size_t len);

static void status_timer_cb(void* arg) {
    static int pct = 87;
    char json[64];
    int n = snprintf(json, sizeof(json), "{\"battery\":%d,\"volume\":50}", pct);
    ble_srv_notify_sts((const uint8_t*)json, n);
}

__attribute__((constructor))
static void status_start(void) {
    const esp_timer_create_args_t t = { .callback = status_timer_cb, .name = "status" };
    esp_timer_handle_t h; esp_timer_create(&t, &h);
    esp_timer_start_periodic(h, 3 * 1000 * 1000); // every 3s
}
