/**************************************************************************************************/
/**
 * @file ble_manager.c
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

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ble_manager.h"
#include "ble_gatt_server.h"
#include "esp_log.h"
#include "esp_peripheral.h"
#include "host/ble_gap.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "state.h"
#include "services/gap/ble_svc_gap.h"

#define BLE_ADV_SERVICE_UUID 0x1811

static const char *s_tag = "NimBLE_BLE_PRPH";

static uint8_t s_own_addr_type;

/**************************************************************************************************/
/**
 * @name ble_store_config_init
 * @brief Initializes the NimBLE persistent storage configuration for bonding and security data.
 *
 *
 *
 */
/**************************************************************************************************/
void ble_store_config_init(void);

/**************************************************************************************************/
/**
 * @name ble_gap_event_handler
 * @brief Handles GAP events such as connection, disconnection, advertising completion,
 *        and security events for logging and state management.
 *
 *
 * @param event
 * @param arg
 *
 * @return int
 */
/**************************************************************************************************/
static int ble_gap_event_handler(struct ble_gap_event *event, void *arg);

static void ble_addr_to_string(const uint8_t *addr, char *out, size_t out_len)
{
    if (addr == NULL || out == NULL || out_len == 0) {
        return;
    }

    snprintf(out,
             out_len,
             "%02X:%02X:%02X:%02X:%02X:%02X",
             addr[5],
             addr[4],
             addr[3],
             addr[2],
             addr[1],
             addr[0]);
}

static void ble_print_conn_desc(struct ble_gap_conn_desc *desc)
{
    MODLOG_DFLT(INFO,
                "handle=%d our_ota_addr_type=%d our_ota_addr=",
                desc->conn_handle,
                desc->our_ota_addr.type);
    print_addr(desc->our_ota_addr.val);

    MODLOG_DFLT(INFO, " our_id_addr_type=%d our_id_addr=", desc->our_id_addr.type);
    print_addr(desc->our_id_addr.val);

    MODLOG_DFLT(INFO, " peer_ota_addr_type=%d peer_ota_addr=", desc->peer_ota_addr.type);
    print_addr(desc->peer_ota_addr.val);

    MODLOG_DFLT(INFO, " peer_id_addr_type=%d peer_id_addr=", desc->peer_id_addr.type);
    print_addr(desc->peer_id_addr.val);

    MODLOG_DFLT(INFO,
                " conn_itvl=%d conn_latency=%d supervision_timeout=%d encrypted=%d authenticated=%d bonded=%d\n",
                desc->conn_itvl,
                desc->conn_latency,
                desc->supervision_timeout,
                desc->sec_state.encrypted,
                desc->sec_state.authenticated,
                desc->sec_state.bonded);
}

static void ble_start_advertising(void)
{
    struct ble_gap_adv_params adv_params;
    struct ble_hs_adv_fields fields;
    const char *name;
    int rc;

    memset(&fields, 0, sizeof(fields));

    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.tx_pwr_lvl_is_present = 1;
    fields.tx_pwr_lvl = BLE_HS_ADV_TX_PWR_LVL_AUTO;

    name = ble_svc_gap_device_name();
    fields.name = (uint8_t *)name;
    fields.name_len = strlen(name);
    fields.name_is_complete = 1;

    fields.uuids16 = (ble_uuid16_t[]){BLE_UUID16_INIT(BLE_ADV_SERVICE_UUID)};
    fields.num_uuids16 = 1;
    fields.uuids16_is_complete = 1;

    rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) {
        MODLOG_DFLT(ERROR, "error setting advertisement data; rc=%d\n", rc);
        return;
    }

    memset(&adv_params, 0, sizeof(adv_params));
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;

    rc = ble_gap_adv_start(s_own_addr_type,
                           NULL,
                           BLE_HS_FOREVER,
                           &adv_params,
                           ble_gap_event_handler,
                           NULL);
    if (rc != 0) {
        MODLOG_DFLT(ERROR, "error enabling advertisement; rc=%d\n", rc);
        return;
    }
}

static int ble_gap_event_handler(struct ble_gap_event *event, void *arg)
{
    (void)arg;

    struct ble_gap_conn_desc desc;
    int rc;

    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT:
            MODLOG_DFLT(INFO,
                        "connection %s; status=%d ",
                        event->connect.status == 0 ? "established" : "failed",
                        event->connect.status);

            if (event->connect.status == 0) {
                rc = ble_gap_conn_find(event->connect.conn_handle, &desc);
                assert(rc == 0);
                ble_print_conn_desc(&desc);

                char peer_addr[VP_BLE_ADDR_MAX_LEN];
                ble_addr_to_string(desc.peer_id_addr.val, peer_addr, sizeof(peer_addr));
                vp_state_set_ble_uuid_addr(peer_addr);
            }

            MODLOG_DFLT(INFO, "\n");

            if (event->connect.status != 0) {
                ble_start_advertising();
            }
            return 0;

        case BLE_GAP_EVENT_DISCONNECT:
            MODLOG_DFLT(INFO, "disconnect; reason=%d ", event->disconnect.reason);
            ble_print_conn_desc(&event->disconnect.conn);
            MODLOG_DFLT(INFO, "\n");
            ble_start_advertising();
            return 0;

        case BLE_GAP_EVENT_CONN_UPDATE:
            MODLOG_DFLT(INFO, "connection updated; status=%d ", event->conn_update.status);
            rc = ble_gap_conn_find(event->conn_update.conn_handle, &desc);
            assert(rc == 0);
            ble_print_conn_desc(&desc);
            MODLOG_DFLT(INFO, "\n");
            return 0;

        case BLE_GAP_EVENT_ADV_COMPLETE:
            MODLOG_DFLT(INFO, "advertise complete; reason=%d", event->adv_complete.reason);
            ble_start_advertising();
            return 0;

        case BLE_GAP_EVENT_ENC_CHANGE:
            MODLOG_DFLT(INFO, "encryption change event; status=%d ", event->enc_change.status);
            rc = ble_gap_conn_find(event->enc_change.conn_handle, &desc);
            assert(rc == 0);
            ble_print_conn_desc(&desc);
            MODLOG_DFLT(INFO, "\n");
            return 0;

        case BLE_GAP_EVENT_NOTIFY_TX:
            MODLOG_DFLT(INFO,
                        "notify_tx event; conn_handle=%d attr_handle=%d status=%d is_indication=%d",
                        event->notify_tx.conn_handle,
                        event->notify_tx.attr_handle,
                        event->notify_tx.status,
                        event->notify_tx.indication);
            return 0;

        case BLE_GAP_EVENT_SUBSCRIBE:
            MODLOG_DFLT(INFO,
                        "subscribe event; conn_handle=%d attr_handle=%d reason=%d prevn=%d curn=%d previ=%d curi=%d\n",
                        event->subscribe.conn_handle,
                        event->subscribe.attr_handle,
                        event->subscribe.reason,
                        event->subscribe.prev_notify,
                        event->subscribe.cur_notify,
                        event->subscribe.prev_indicate,
                        event->subscribe.cur_indicate);
            return 0;

        case BLE_GAP_EVENT_MTU:
            MODLOG_DFLT(INFO,
                        "mtu update event; conn_handle=%d cid=%d mtu=%d\n",
                        event->mtu.conn_handle,
                        event->mtu.channel_id,
                        event->mtu.value);
            return 0;

        case BLE_GAP_EVENT_REPEAT_PAIRING:
            rc = ble_gap_conn_find(event->repeat_pairing.conn_handle, &desc);
            assert(rc == 0);
            ble_store_util_delete_peer(&desc.peer_id_addr);
            return BLE_GAP_REPEAT_PAIRING_RETRY;
    }

    return 0;
}

static void ble_on_reset(int reason)
{
    MODLOG_DFLT(ERROR, "Resetting state; reason=%d\n", reason);
}

static void ble_on_sync(void)
{
    int rc;

    rc = ble_hs_util_ensure_addr(0);
    assert(rc == 0);

    rc = ble_hs_id_infer_auto(0, &s_own_addr_type);
    if (rc != 0) {
        MODLOG_DFLT(ERROR, "error determining address type; rc=%d\n", rc);
        return;
    }

    uint8_t addr_val[6] = {0};
    rc = ble_hs_id_copy_addr(s_own_addr_type, addr_val, NULL);
    if (rc == 0) {
        char own_addr[VP_BLE_ADDR_MAX_LEN];
        ble_addr_to_string(addr_val, own_addr, sizeof(own_addr));
        vp_state_set_ble_uuid_addr(own_addr);

        MODLOG_DFLT(INFO, "Device Address: ");
        print_addr(addr_val);
        MODLOG_DFLT(INFO, "\n");
    }

    ble_start_advertising();
}

static void ble_host_task(void *param)
{
    (void)param;

    ESP_LOGI(s_tag, "BLE Host Task Started");
    nimble_port_run();
    nimble_port_freertos_deinit();
}

esp_err_t ble_manager_init(void)
{
    int rc;
    esp_err_t err;

    err = nimble_port_init();
    if (err != ESP_OK) {
        ESP_LOGE(s_tag, "Failed to init nimble: %d", err);
        return err;
    }

    ble_hs_cfg.reset_cb = ble_on_reset;
    ble_hs_cfg.sync_cb = ble_on_sync;
    ble_hs_cfg.gatts_register_cb = ble_gatt_server_register_cb;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

    ble_hs_cfg.sm_io_cap = CONFIG_EXAMPLE_IO_TYPE;
    ble_hs_cfg.sm_sc = 0;

    rc = ble_gatt_server_init();
    if (rc != 0) {
        ESP_LOGE(s_tag, "ble_gatt_server_init failed: %d", rc);
        return ESP_FAIL;
    }

    rc = ble_svc_gap_device_name_set("VocalPoint");
    if (rc != 0) {
        ESP_LOGE(s_tag, "ble_svc_gap_device_name_set failed: %d", rc);
        return ESP_FAIL;
    }

    ble_store_config_init();
    nimble_port_freertos_init(ble_host_task);

    return ESP_OK;
}
