#include "esp_log.h"
#include "esp_gatts_api.h"
#include "esp_gap_ble_api.h"
#include "esp_bt_main.h"

static const char *TAG = "BLE_SRV";

/* UUIDs */
#define UUID_SVC   0xABF0
#define UUID_CMD   0xABF1
#define UUID_EVT   0xABF2
#define UUID_STS   0xABF3

static uint16_t g_gatts_if = 0, g_conn_id = 0;
static uint16_t h_service = 0, h_cmd = 0, h_evt = 0, h_sts = 0;

extern void evtbus_notify_event(const uint8_t *data, size_t len);
extern void status_notify_snapshot(void);
extern void cmd_handle_write(const uint8_t *data, uint16_t len);

/* GAP advertise */
static void start_advertising(void) {
    esp_ble_adv_params_t adv_params = {
        .adv_int_min = 0x50, .adv_int_max = 0x60,
        .adv_type = ADV_TYPE_IND, .own_addr_type = BLE_ADDR_TYPE_PUBLIC,
        .channel_map = ADV_CHNL_ALL, .adv_filter_policy = ADV_FILTER_ALLOW_SCAN_ANY_CON_ANY
    };
    uint8_t service_uuid[2] = { UUID_SVC & 0xFF, (UUID_SVC >> 8) & 0xFF };
    esp_ble_adv_data_t adv = {
        .set_scan_rsp = false,
        .include_name = true,
        .include_txpower = false,
        .flag = (ESP_BLE_ADV_FLAG_GEN_DISC | ESP_BLE_ADV_FLAG_BREDR_NOT_SPT),
        .service_uuid_len = sizeof(service_uuid),
        .p_service_uuid = service_uuid,
    };
    esp_ble_gap_config_adv_data(&adv);
    esp_ble_gap_start_advertising(&adv_params);
}

static void gap_cb(esp_gap_ble_cb_event_t e, esp_ble_gap_cb_param_t *p) {
    if (e == ESP_GAP_BLE_ADV_DATA_SET_COMPLETE_EVT) start_advertising();
}

static void gatts_cb(esp_gatts_cb_event_t e, esp_gatt_if_t ifx, esp_ble_gatts_cb_param_t *p) {
    switch (e) {
    case ESP_GATTS_REG_EVT: {
        g_gatts_if = ifx;
        esp_ble_gap_register_callback(gap_cb);
        esp_ble_gap_set_device_name("VocalPoint");
        // Create service
        esp_gatt_srvc_id_t sid = {.is_primary = true, .id = {.inst_id = 0, .uuid = {.len=ESP_UUID_LEN_16, .uuid={.uuid16=UUID_SVC}}}};
        esp_ble_gatts_create_service(ifx, &sid, 8);
        break;
    }
    case ESP_GATTS_CREATE_EVT: {
        h_service = p->create.service_handle;
        // CMD characteristic (Write Without Response)
        esp_bt_uuid_t cuuid = {.len=ESP_UUID_LEN_16, .uuid={.uuid16=UUID_CMD}};
        esp_gatt_char_prop_t cprop = ESP_GATT_CHAR_PROP_BIT_WRITE_NR;
        esp_attr_control_t ctrl = {.auto_rsp = ESP_GATT_AUTO_RSP};
        esp_attr_value_t val = {.attr_max_len=128, .attr_len=1, .attr_value=(uint8_t*)""};
        esp_ble_gatts_add_char(h_service, &cuuid, ESP_GATT_PERM_WRITE, cprop, &val, &ctrl);

        // EVT characteristic (Notify)
        esp_bt_uuid_t euuid = {.len=ESP_UUID_LEN_16, .uuid={.uuid16=UUID_EVT}};
        esp_gatt_char_prop_t eprop = ESP_GATT_CHAR_PROP_BIT_NOTIFY;
        esp_ble_gatts_add_char(h_service, &euuid, ESP_GATT_PERM_READ, eprop, &val, &ctrl);

        // STS characteristic (Read + Notify)
        esp_bt_uuid_t suuid = {.len=ESP_UUID_LEN_16, .uuid={.uuid16=UUID_STS}};
        esp_gatt_char_prop_t sprop = ESP_GATT_CHAR_PROP_BIT_READ | ESP_GATT_CHAR_PROP_BIT_NOTIFY;
        esp_ble_gatts_add_char(h_service, &suuid, ESP_GATT_PERM_READ, sprop, &val, &ctrl);

        esp_ble_gatts_start_service(h_service);
        break;
    }
    case ESP_GATTS_ADD_CHAR_EVT: {
        if (p->add_char.char_uuid.uuid.uuid16 == UUID_CMD) h_cmd = p->add_char.attr_handle;
        if (p->add_char.char_uuid.uuid.uuid16 == UUID_EVT) h_evt = p->add_char.attr_handle;
        if (p->add_char.char_uuid.uuid.uuid16 == UUID_STS) h_sts = p->add_char.attr_handle;
        break;
    }
    case ESP_GATTS_CONNECT_EVT:
        g_conn_id = p->connect.conn_id;
        break;
    case ESP_GATTS_WRITE_EVT:
        if (p->write.handle == h_cmd) cmd_handle_write(p->write.value, p->write.len);
        break;
    default: break;
    }
}

void ble_srv_init(void) {
    esp_ble_gatts_register_callback(gatts_cb);
    esp_ble_gatts_app_register(0x42);
}

/* called by evt_bus/status_mgr to push notifies */
void ble_srv_notify_evt(const uint8_t *data, size_t len) {
    if (g_gatts_if && h_evt) esp_ble_gatts_send_indicate(g_gatts_if, g_conn_id, h_evt, len, (uint8_t*)data, false);
}
void ble_srv_notify_sts(const uint8_t *data, size_t len) {
    if (g_gatts_if && h_sts) esp_ble_gatts_send_indicate(g_gatts_if, g_conn_id, h_sts, len, (uint8_t*)data, false);
}
