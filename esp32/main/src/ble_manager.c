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
#include <inttypes.h>
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

#if CONFIG_EXAMPLE_RANDOM_ADDR
static uint8_t s_own_addr_type = BLE_OWN_ADDR_RANDOM;
#else
static uint8_t s_own_addr_type;
#endif

#if CONFIG_EXAMPLE_EXTENDED_ADV
static uint8_t s_ext_adv_pattern[] = {
    0x02, 0x01, 0x06,
    0x03, 0x03, 0xab, 0xcd,
    0x03, 0x03, 0x18, 0x11,
    0x11, 0X09, 'n', 'i', 'm', 'b', 'l', 'e', '-', 'b', 'l', 'e', 'p', 'r', 'p', 'h', '-', 'e',
};
#endif

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

#if CONFIG_EXAMPLE_EXTENDED_ADV
static void ble_start_advertising(void)
{
    struct ble_gap_ext_adv_params params;
    struct os_mbuf *data;
    uint8_t instance = 0;
    int rc;

    if (ble_gap_ext_adv_active(instance)) {
        return;
    }

    memset(&params, 0, sizeof(params));
    params.connectable = 1;
    params.own_addr_type = BLE_OWN_ADDR_PUBLIC;
    params.primary_phy = BLE_HCI_LE_PHY_1M;
    params.secondary_phy = BLE_HCI_LE_PHY_2M;
    params.sid = 1;
    params.itvl_min = BLE_GAP_ADV_FAST_INTERVAL1_MIN;
    params.itvl_max = BLE_GAP_ADV_FAST_INTERVAL1_MIN;

    rc = ble_gap_ext_adv_configure(instance, &params, NULL, ble_gap_event_handler, NULL);
    assert(rc == 0);

    data = os_msys_get_pkthdr(sizeof(s_ext_adv_pattern), 0);
    assert(data != NULL);

    rc = os_mbuf_append(data, s_ext_adv_pattern, sizeof(s_ext_adv_pattern));
    assert(rc == 0);

    rc = ble_gap_ext_adv_set_data(instance, data);
    assert(rc == 0);

    rc = ble_gap_ext_adv_start(instance, 0, 0);
    assert(rc == 0);
}
#else
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
#endif

#if MYNEWT_VAL(BLE_POWER_CONTROL)
static void ble_enable_power_control(uint16_t conn_handle)
{
    int rc;

    rc = ble_gap_read_remote_transmit_power_level(conn_handle, 0x01);
    assert(rc == 0);

    rc = ble_gap_set_transmit_power_reporting_enable(conn_handle, 0x1, 0x1);
    assert(rc == 0);
}
#endif

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

#if MYNEWT_VAL(BLE_POWER_CONTROL)
            ble_enable_power_control(event->connect.conn_handle);
#endif
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

        case BLE_GAP_EVENT_PASSKEY_ACTION: {
            ESP_LOGI(s_tag, "PASSKEY_ACTION_EVENT started");

            struct ble_sm_io passkey_io = {0};
            int key = 0;

            if (event->passkey.params.action == BLE_SM_IOACT_DISP) {
                passkey_io.action = event->passkey.params.action;
                passkey_io.passkey = 123456;
                ESP_LOGI(s_tag,
                         "Enter passkey %" PRIu32 " on the peer side",
                         passkey_io.passkey);
                rc = ble_sm_inject_io(event->passkey.conn_handle, &passkey_io);
                ESP_LOGI(s_tag, "ble_sm_inject_io result: %d", rc);
            } else if (event->passkey.params.action == BLE_SM_IOACT_NUMCMP) {
                ESP_LOGI(s_tag,
                         "Passkey on device's display: %" PRIu32,
                         event->passkey.params.numcmp);
                ESP_LOGI(s_tag,
                         "Accept or reject passkey via console: key Y or key N");

                passkey_io.action = event->passkey.params.action;
                if (scli_receive_key(&key)) {
                    passkey_io.numcmp_accept = key;
                } else {
                    passkey_io.numcmp_accept = 0;
                    ESP_LOGE(s_tag, "Timeout, rejecting key");
                }

                rc = ble_sm_inject_io(event->passkey.conn_handle, &passkey_io);
                ESP_LOGI(s_tag, "ble_sm_inject_io result: %d", rc);
            } else if (event->passkey.params.action == BLE_SM_IOACT_OOB) {
                static uint8_t oob[16] = {0};

                passkey_io.action = event->passkey.params.action;
                for (int i = 0; i < 16; i++) {
                    passkey_io.oob[i] = oob[i];
                }

                rc = ble_sm_inject_io(event->passkey.conn_handle, &passkey_io);
                ESP_LOGI(s_tag, "ble_sm_inject_io result: %d", rc);
            } else if (event->passkey.params.action == BLE_SM_IOACT_INPUT) {
                ESP_LOGI(s_tag,
                         "Enter passkey via console in format: key 123456");
                passkey_io.action = event->passkey.params.action;

                if (scli_receive_key(&key)) {
                    passkey_io.passkey = key;
                } else {
                    passkey_io.passkey = 0;
                    ESP_LOGE(s_tag, "Timeout, passing 0 as key");
                }

                rc = ble_sm_inject_io(event->passkey.conn_handle, &passkey_io);
                ESP_LOGI(s_tag, "ble_sm_inject_io result: %d", rc);
            }

            return 0;
        }

        case BLE_GAP_EVENT_AUTHORIZE:
            MODLOG_DFLT(INFO,
                        "authorize event: conn_handle=%d attr_handle=%d is_read=%d",
                        event->authorize.conn_handle,
                        event->authorize.attr_handle,
                        event->authorize.is_read);
            event->authorize.out_response = BLE_GAP_AUTHORIZE_REJECT;
            return 0;

#if MYNEWT_VAL(BLE_POWER_CONTROL)
        case BLE_GAP_EVENT_TRANSMIT_POWER:
            MODLOG_DFLT(INFO,
                        "Transmit power event : status=%d conn_handle=%d reason=%d phy=%d power_level=%x power_level_flag=%d delta=%d",
                        event->transmit_power.status,
                        event->transmit_power.conn_handle,
                        event->transmit_power.reason,
                        event->transmit_power.phy,
                        event->transmit_power.transmit_power_level,
                        event->transmit_power.transmit_power_level_flag,
                        event->transmit_power.delta);
            return 0;

        case BLE_GAP_EVENT_PATHLOSS_THRESHOLD:
            MODLOG_DFLT(INFO,
                        "Pathloss threshold event : conn_handle=%d current path loss=%d zone_entered=%d",
                        event->pathloss_threshold.conn_handle,
                        event->pathloss_threshold.current_path_loss,
                        event->pathloss_threshold.zone_entered);
            return 0;
#endif
    }

    return 0;
}

static void ble_on_reset(int reason)
{
    MODLOG_DFLT(ERROR, "Resetting state; reason=%d\n", reason);
}

#if CONFIG_EXAMPLE_RANDOM_ADDR
static void ble_set_random_addr(void)
{
    ble_addr_t addr;
    int rc;

    rc = ble_hs_id_gen_rnd(0, &addr);
    assert(rc == 0);

    rc = ble_hs_id_set_rnd(addr.val);
    assert(rc == 0);
}
#endif

static void ble_on_sync(void)
{
    int rc;

#if CONFIG_EXAMPLE_RANDOM_ADDR
    ble_set_random_addr();
    rc = ble_hs_util_ensure_addr(1);
#else
    rc = ble_hs_util_ensure_addr(0);
#endif
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
#ifdef CONFIG_EXAMPLE_BONDING
    ble_hs_cfg.sm_bonding = 1;
    ble_hs_cfg.sm_our_key_dist |= BLE_SM_PAIR_KEY_DIST_ENC;
    ble_hs_cfg.sm_their_key_dist |= BLE_SM_PAIR_KEY_DIST_ENC;
#endif
#ifdef CONFIG_EXAMPLE_MITM
    ble_hs_cfg.sm_mitm = 1;
#endif
#ifdef CONFIG_EXAMPLE_USE_SC
    ble_hs_cfg.sm_sc = 1;
#else
    ble_hs_cfg.sm_sc = 0;
#endif
#ifdef CONFIG_EXAMPLE_RESOLVE_PEER_ADDR
    ble_hs_cfg.sm_our_key_dist |= BLE_SM_PAIR_KEY_DIST_ID;
    ble_hs_cfg.sm_their_key_dist |= BLE_SM_PAIR_KEY_DIST_ID;
#endif

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

    rc = scli_init();
    if (rc != ESP_OK) {
        ESP_LOGE(s_tag, "scli_init failed");
        return ESP_FAIL;
    }

    return ESP_OK;
}
