#include <stddef.h>
#include <string.h>

extern void ble_srv_notify_evt(const uint8_t *data, size_t len);

void evtbus_notify_event(const uint8_t *data, size_t len) {
    ble_srv_notify_evt(data, len);
}
