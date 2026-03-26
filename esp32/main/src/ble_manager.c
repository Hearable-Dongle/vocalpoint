/**************************************************************************************************/
/**
 * @file ble_manager.c
 * @brief BLE manager module for GAP event handling, advertisement management, and connection
 *        lifecycle.
 *
 * @version 0.1
 * @date 2026-03-03
 *
 * @copyright Copyright (c) 2026
 *
 */
/**************************************************************************************************/


/***************************************************************************************************
 * Includes
 **************************************************************************************************/

// Standard includes
#include <assert.h>
#include <stdio.h>
#include <string.h>

// Third-party includes
#include "esp_log.h"
#include "esp_peripheral.h"
#include "host/ble_gap.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"

// Project includes
#include "ble_manager.h"
#include "ble_gatt_server.h"
#include "log.h"
#include "state.h"


/***************************************************************************************************
 * Variable Declarations
 **************************************************************************************************/

static uint8_t s_own_addr_type;


/***************************************************************************************************
 * Function Declarations
 **************************************************************************************************/

/**************************************************************************************************/
/**
 * @name ble_gap_event_handler
 * @brief Handles GAP events such as connection, disconnection, advertising completion, and security
 *        events for logging and state management.
 *
 * @param event Pointer to the GAP event structure containing event type and event-specific data.
 * @param arg User-provided argument passed to the GAP event handler (typically NULL).
 *
 * @return int Zero to indicate successful event handling, or event-specific return codes.
 */
/**************************************************************************************************/
static int ble_gap_event_handler(struct ble_gap_event *event, void *arg);


/***************************************************************************************************
 * Function Definitions
 **************************************************************************************************/

/**************************************************************************************************/
/**
 * @name ble_convert_addr
 * @brief Converts a 6-byte BLE address to a colon-separated uppercase string.
 *
 * @param p_addr Pointer to the 6-byte BLE address.
 * @param p_string Output buffer that receives the formatted address string.
 * @param p_string_len Size of @p p_string in bytes.
 *
 * @return void
 */
/**************************************************************************************************/
static void ble_convert_addr(const uint8_t *p_addr, char *p_string, size_t p_string_len)
{
    // Validate input parameters.
    if (p_addr != NULL && p_string != NULL && p_string_len > 0)
    {
        // Format the address as a standard MAC address string.
        snprintf(
            p_string,
            p_string_len,
            "%02X:%02X:%02X:%02X:%02X:%02X",
            p_addr[5],
            p_addr[4],
            p_addr[3],
            p_addr[2],
            p_addr[1],
            p_addr[0]
        );
    }
    else
    {
        // Log an error if the input parameters are invalid.
        ESP_LOGE(s_tag, "Invalid parameters for address conversion.");
    }
}

/**************************************************************************************************/
/**
 * @name ble_log_conn
 * @brief Logs BLE connection descriptor details in a human-readable format.
 *
 * @param p_desc Pointer to the BLE connection descriptor.
 *
 * @return void
 */
/**************************************************************************************************/
static void ble_log_conn(struct ble_gap_conn_desc *p_desc)
{
    // Validate input parameters
    if (p_desc != NULL)
    {
        // Declare a buffer to hold the formatted address strings.
        char our_ota_addr[VP_BLE_ADDR_MAX_LEN];
        char our_id_addr[VP_BLE_ADDR_MAX_LEN];
        char peer_ota_addr[VP_BLE_ADDR_MAX_LEN];
        char peer_id_addr[VP_BLE_ADDR_MAX_LEN];

        // Convert address to string for logging
        ble_convert_addr(p_desc->our_ota_addr.val, our_ota_addr, sizeof(our_ota_addr));
        ble_convert_addr(p_desc->our_id_addr.val, our_id_addr, sizeof(our_id_addr));
        ble_convert_addr(p_desc->peer_ota_addr.val, peer_ota_addr, sizeof(peer_ota_addr));
        ble_convert_addr(p_desc->peer_id_addr.val, peer_id_addr, sizeof(peer_id_addr));

        // Log connection details in a human-readable format.
        ESP_LOGI(
            s_tag,
            "Requested connection details.\n"
            "\thandle=%d\n"
            "\tour_ota_addr_type=%d\n"
            "\tour_ota_addr=%s\n"
            "\tour_id_addr_type=%d\n"
            "\tour_id_addr=%s\n"
            "\tpeer_ota_addr_type=%d\n"
            "\tpeer_ota_addr=%s\n"
            "\tpeer_id_addr_type=%d\n"
            "\tpeer_id_addr=%s\n"
            "\tconn_itvl=%d\n"
            "\tconn_latency=%d\n"
            "\tsupervision_timeout=%d\n"
            "\tencrypted=%d\n"
            "\tauthenticated=%d\n"
            "\tbonded=%d\n",
            p_desc->conn_handle,
            p_desc->our_ota_addr.type,
            our_ota_addr,
            p_desc->our_id_addr.type,
            our_id_addr,
            p_desc->peer_ota_addr.type,
            peer_ota_addr,
            p_desc->peer_id_addr.type,
            peer_id_addr,
            p_desc->conn_itvl,
            p_desc->conn_latency,
            p_desc->supervision_timeout,
            p_desc->sec_state.encrypted,
            p_desc->sec_state.authenticated,
            p_desc->sec_state.bonded
        );
    }
    else
    {
        // Log an error if the input parameters are invalid.
        ESP_LOGE(s_tag, "Invalid parameters for connection logging.");
    }
}

/**************************************************************************************************/
/**
 * @name ble_start_advertising
 * @brief Configures and initiates BLE advertisement with device name, service UUID, and TX power.
 *
 * This function sets up advertisement fields including device name, service UUIDs, and TX power
 * level, then starts continuous undirected general discoverable advertising. Any errors during
 * configuration or advertisement startup are logged but do not halt execution.
 *
 * @return void
 */
/**************************************************************************************************/
static void ble_start_advertising(void)
{
    // Define return code variable for error handling.
    int ret_code = 0;

    // Declare advertising data and parameters.
    struct ble_hs_adv_fields fields;
    struct ble_gap_adv_params params;
    
    // Ensure advertising data and parameters are zero-initialized.
    memset(&fields, 0, sizeof(fields));
    memset(&params, 0, sizeof(params));

    // Set the device name in the advertising data.
    const char *name = (const char *)ble_svc_gap_device_name();
    fields.name = (uint8_t *)name;
    fields.name_len = strlen(name);
    fields.name_is_complete = 1;

    // Set the service UUIDs in the advertising data.
    fields.uuids16 = (ble_uuid16_t[]){BLE_UUID16_INIT(BLE_ADV_SERVICE_UUID)};
    fields.num_uuids16 = 1;
    fields.uuids16_is_complete = 1;

    // Set the advertising flags.
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;

    // Set the advertising TX power level.
    fields.tx_pwr_lvl_is_present = 1;
    fields.tx_pwr_lvl = BLE_HS_ADV_TX_PWR_LVL_AUTO;

    // Configure advertising parameters for undirected connectable mode.
    params.conn_mode = BLE_GAP_CONN_MODE_UND;
    params.disc_mode = BLE_GAP_DISC_MODE_GEN;

    // Set the advertising data and handle any errors.
    ret_code = ble_gap_adv_set_fields(&fields);
    if (ret_code != 0)
    {
        ESP_LOGE(
            s_tag,
            "Unsuccessful setting advertisement data\n"
            "\tret_code=%d\n",
            ret_code
        );
    }

    // Start advertising and handle any errors.
    ret_code = ble_gap_adv_start(
        s_own_addr_type,
        NULL,
        BLE_HS_FOREVER,
        &params,
        ble_gap_event_handler,
        NULL
    );
    if (ret_code != 0)
    {
        ESP_LOGE(
            s_tag,
            "Unsuccessful enabling advertisement.\n"
            "\tret_code=%d\n",
            ret_code
        );
    }
}

/**************************************************************************************************/
/**
 * @name ble_gap_event_handler
 * @brief Handles GAP events such as connection, disconnection, advertising completion, and security
 *        events for logging and state management.
 *
 * @param event Pointer to the GAP event structure containing event type and event-specific data.
 * @param arg User-provided argument passed to the GAP event handler (typically NULL).
 *
 * @return int Zero to indicate successful event handling, or event-specific return codes.
 */
/**************************************************************************************************/
static int ble_gap_event_handler(struct ble_gap_event *event, void *arg)
{
    (void)arg;

    struct ble_gap_conn_desc desc;
    int rc;

    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT:
            ESP_LOGI(s_tag,
                     "connection %s; status=%d ",
                     event->connect.status == 0 ? "established" : "failed",
                     event->connect.status);

            if (event->connect.status == 0) {
                rc = ble_gap_conn_find(event->connect.conn_handle, &desc);
                assert(rc == 0);
                ble_log_conn(&desc);

                char peer_addr[VP_BLE_ADDR_MAX_LEN];
                ble_convert_addr(desc.peer_id_addr.val,
                                 peer_addr,
                                 sizeof(peer_addr));
                vp_state_set_ble_uuid_addr(peer_addr);
            }

            ESP_LOGI(s_tag, "\n");

            if (event->connect.status != 0) {
                ble_start_advertising();
            }
            return 0;

        case BLE_GAP_EVENT_DISCONNECT:
            ESP_LOGI(s_tag, "disconnect; reason=%d ", event->disconnect.reason);
            ble_log_conn(&event->disconnect.conn);
            ESP_LOGI(s_tag, "\n");
            ble_start_advertising();
            return 0;

        case BLE_GAP_EVENT_CONN_UPDATE:
            ESP_LOGI(s_tag, "connection updated; status=%d ", event->conn_update.status);
            rc = ble_gap_conn_find(event->conn_update.conn_handle, &desc);
            assert(rc == 0);
            ble_log_conn(&desc);
            ESP_LOGI(s_tag, "\n");
            return 0;

        case BLE_GAP_EVENT_ADV_COMPLETE:
            ESP_LOGI(s_tag, "advertise complete; reason=%d", event->adv_complete.reason);
            ble_start_advertising();
            return 0;

        case BLE_GAP_EVENT_ENC_CHANGE:
            ESP_LOGI(s_tag, "encryption change event; status=%d ", event->enc_change.status);
            rc = ble_gap_conn_find(event->enc_change.conn_handle, &desc);
            assert(rc == 0);
            ble_log_conn(&desc);
            ESP_LOGI(s_tag, "\n");
            return 0;

        case BLE_GAP_EVENT_NOTIFY_TX:
            ESP_LOGI(s_tag,
                     "notify_tx event; conn_handle=%d attr_handle=%d status=%d is_indication=%d",
                     event->notify_tx.conn_handle,
                     event->notify_tx.attr_handle,
                     event->notify_tx.status,
                     event->notify_tx.indication);
            return 0;

        case BLE_GAP_EVENT_SUBSCRIBE:
            ESP_LOGI(s_tag,
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
            ESP_LOGI(s_tag,
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
    ESP_LOGI(s_tag, "Resetting state; reason=%d\n", reason);
}

static void ble_on_sync(void)
{
    int rc;

    rc = ble_hs_util_ensure_addr(0);
    assert(rc == 0);

    rc = ble_hs_id_infer_auto(0, &s_own_addr_type);
    if (rc != 0) {
        ESP_LOGI(s_tag, "error determining address type; rc=%d\n", rc);
        return;
    }

    uint8_t addr_val[6] = {0};
    rc = ble_hs_id_copy_addr(s_own_addr_type, addr_val, NULL);
    if (rc == 0) {
        char own_addr[VP_BLE_ADDR_MAX_LEN];
        ble_convert_addr(addr_val, own_addr, sizeof(own_addr));
        vp_state_set_ble_uuid_addr(own_addr);

        ESP_LOGI(s_tag, "Device Address: ");
        print_addr(addr_val);
        ESP_LOGI(s_tag, "\n");
    }

    ble_start_advertising();
}

static void ble_host_task(void *param)
{
    (void)param;

    ESP_LOGI(s_tag, "BLE Host Task Started\n");
    nimble_port_run();
    nimble_port_freertos_deinit();
}

esp_err_t ble_manager_init(void)
{
    int rc;
    esp_err_t err;

    err = nimble_port_init();
    if (err != ESP_OK) {
        ESP_LOGI(s_tag, "Failed to init nimble: %d\n", err);
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
        ESP_LOGI(s_tag, "ble_gatt_server_init failed: %d\n", rc);
        return ESP_FAIL;
    }

    rc = ble_svc_gap_device_name_set("VocalPoint");
    if (rc != 0) {
        ESP_LOGI(s_tag, "ble_svc_gap_device_name_set failed: %d\n", rc);
        return ESP_FAIL;
    }

    ble_store_config_init();
    nimble_port_freertos_init(ble_host_task);

    return ESP_OK;
}
