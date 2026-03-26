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

static uint8_t own_addr_type;


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
static void ble_convert_addr(unsigned char *p_addr, char *p_string, size_t p_string_len)
{
    // Validate input parameters.
    if (p_addr != NULL && p_string != NULL && p_string_len > 0)
    {
        // Format address as a standard MAC address string.
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
        // Log an error if input parameters are invalid.
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
        // Declare a buffer to hold formatted address strings.
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
        // Log an error if input parameters are invalid.
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

    // Set device name in advertising data.
    const char *name = (const char *)ble_svc_gap_device_name();
    fields.name = (uint8_t *)name;
    fields.name_len = strlen(name);
    fields.name_is_complete = 1;

    // Set service UUIDs in advertising data.
    fields.uuids16 = (ble_uuid16_t[]){BLE_UUID16_INIT(BLE_ADV_SERVICE_UUID)};
    fields.num_uuids16 = 1;
    fields.uuids16_is_complete = 1;

    // Set advertising flags.
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;

    // Set advertising TX power level.
    fields.tx_pwr_lvl_is_present = 1;
    fields.tx_pwr_lvl = BLE_HS_ADV_TX_PWR_LVL_AUTO;

    // Configure advertising parameters for undirected connectable mode.
    params.conn_mode = BLE_GAP_CONN_MODE_UND;
    params.disc_mode = BLE_GAP_DISC_MODE_GEN;

    // Set advertising data and handle any errors.
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
        own_addr_type,
        NULL,
        BLE_HS_FOREVER,
        &params,
        ble_gap_event_handler,
        NULL
    );
    if (ret_code != 0)
    {
        // Log an error if advertisement startup fails.
        ESP_LOGE(
            s_tag,
            "Unsuccessful starting advertisement.\n"
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
    // Define return code variable for error handling.
    int ret_code = 0;

    // Declare a connection descriptor for use in events that require connection information.
    struct ble_gap_conn_desc desc;

    // Handle GAP event based on type.
    switch (event->type)
    {
        // Handle connection events.
        case BLE_GAP_EVENT_CONNECT:

            // Log event and connection status.
            ESP_LOGI(
                s_tag,
                "Connection event triggered.\n"
                "\tstatus=%s\n",
                event->connect.status == 0 ? "established" : "failed"
            );

            // Verify connection was successful.
            if (event->connect.status == 0)
            {
                // Retrieve connection details and handle any errors.
                ret_code = ble_gap_conn_find(event->connect.conn_handle, &desc);
                if (ret_code == 0)
                {
                    // Log connection details
                    ble_log_conn(&desc);

                    // Update BLE address in shared state for display and diagnostics.
                    char peer_addr[VP_BLE_ADDR_MAX_LEN];
                    ble_convert_addr(desc.peer_id_addr.val, peer_addr, sizeof(peer_addr));
                    vp_state_set_ble_uuid_addr(peer_addr);
                }
                else
                {
                    // Log an error if connection descriptor is not found.
                    ESP_LOGE(
                        s_tag,
                        "Failed to find connection descriptor for new connection.\n"
                        "\tconn_handle=%d\n"
                        "\tret_code=%d\n",
                        event->connect.conn_handle,
                        ret_code
                    );
                }
            }
            else
            {
                // Start advertising again if connection attempt failed.
                ble_start_advertising();
            }

            // Break from switch statement after handling event.
            break;

        // Handle disconnection events.
        case BLE_GAP_EVENT_DISCONNECT:

            // Log event and disconnection reason.
            ESP_LOGI(
                s_tag,
                "Disconnect event triggered.\n"
                "\treason=%d\n",
                event->disconnect.reason
            );

            // Log connection details for disconnected connection.
            ble_log_conn(&event->disconnect.conn);

            // Start advertising again to allow new connections after disconnection.
            ble_start_advertising();
            
            // Break from switch statement after handling event.
            break;

        // Handle connection update events.
        case BLE_GAP_EVENT_CONN_UPDATE:

            // Log event and connection update status.
            ESP_LOGI(
                s_tag,
                "Connection update event triggered.\n"
                "\tstatus=%d\n",
                event->conn_update.status
            );

            // Retrieve connection details and handle any errors.
            ret_code = ble_gap_conn_find(event->conn_update.conn_handle, &desc);
            if (ret_code == 0)
            {
                // Log connection details
                ble_log_conn(&desc);
            }
            else
            {
                // Log an error if connection descriptor is not found.
                ESP_LOGE(
                    s_tag,
                    "Failed to find connection descriptor for current connection.\n"
                    "\tconn_handle=%d\n"
                    "\tret_code=%d\n",
                    event->conn_update.conn_handle,
                    ret_code
                );
            }
            
            // Break from switch statement after handling event.
            break;

        // Handle advertising completion events.
        case BLE_GAP_EVENT_ADV_COMPLETE:

            // Log event and advertising reason.
            ESP_LOGI(
                s_tag,
                "Advertising complete event triggered.\n"
                "\treason=%d\n",
                event->adv_complete.reason
            );

            // Start advertising again to maintain continuous advertising.
            ble_start_advertising();
            
            // Break from switch statement after handling event.
            break;

        // Handle encryption change events.
        case BLE_GAP_EVENT_ENC_CHANGE:

            // Log event and encryption change status.
            ESP_LOGI(
                s_tag,
                "Encryption change event triggered.\n"
                "\tstatus=%d\n",
                event->enc_change.status
            );

            // Retrieve connection details and handle any errors.
            ret_code = ble_gap_conn_find(event->enc_change.conn_handle, &desc);
            if (ret_code == 0)
            {
                // Log connection details
                ble_log_conn(&desc);
            }
            else
            {
                // Log an error if connection descriptor is not found.
                ESP_LOGE(
                    s_tag,
                    "Failed to find connection descriptor for current connection.\n"
                    "\tconn_handle=%d\n"
                    "\tret_code=%d\n",
                    event->enc_change.conn_handle,
                    ret_code
                );
            }
            
            // Break from switch statement after handling event.
            break;

        // Handle notification transmission events.
        case BLE_GAP_EVENT_NOTIFY_TX:

            // Log event and notification transmission details.
            ESP_LOGI(
                s_tag,
                "Notification transmission event triggered.\n"
                "\tstatus=%d\n"
                "\tattr_handle=%d\n"
                "\tis_indication=%d\n",
                event->notify_tx.status,
                event->notify_tx.attr_handle,
                event->notify_tx.indication
            );

            // Retrieve connection details and handle any errors.
            ret_code = ble_gap_conn_find(event->notify_tx.conn_handle, &desc);
            if (ret_code == 0)
            {
                // Log connection details
                ble_log_conn(&desc);
            }
            else
            {
                // Log an error if connection descriptor is not found.
                ESP_LOGE(
                    s_tag,
                    "Failed to find connection descriptor for current connection.\n"
                    "\tconn_handle=%d\n"
                    "\tret_code=%d\n",
                    event->notify_tx.conn_handle,
                    ret_code
                );
            }
            
            // Break from switch statement after handling event.
            break;

        // Handle subscription events.
        case BLE_GAP_EVENT_SUBSCRIBE:

            // Log event and subscription details.
            ESP_LOGI(s_tag,
                "Subscription event triggered.\n"
                "\tattr_handle=%d\n"
                "\treason=%d\n"
                "\tprev_notify=%d\n"
                "\tcur_notify=%d\n"
                "\tprev_indicate=%d\n"
                "\tcur_indicate=%d\n",
                event->subscribe.attr_handle,
                event->subscribe.reason,
                event->subscribe.prev_notify,
                event->subscribe.cur_notify,
                event->subscribe.prev_indicate,
                event->subscribe.cur_indicate
            );

            // Retrieve connection details and handle any errors.
            ret_code = ble_gap_conn_find(event->subscribe.conn_handle, &desc);
            if (ret_code == 0)
            {
                // Log connection details
                ble_log_conn(&desc);
            }
            else
            {
                // Log an error if connection descriptor is not found.
                ESP_LOGE(
                    s_tag,
                    "Failed to find connection descriptor for current connection.\n"
                    "\tconn_handle=%d\n"
                    "\tret_code=%d\n",
                    event->subscribe.conn_handle,
                    ret_code
                );
            }
            
            // Break from switch statement after handling event.
            break;

        // Handle packet size update events.
        case BLE_GAP_EVENT_MTU:

            // Log event and MTU details.
            ESP_LOGI(
                s_tag,
                "MTU update event triggered.\n"
                "\tconn_handle=%d\n"
                "\tcid=%d\n"
                "\tmtu=%d\n",
                event->mtu.conn_handle,
                event->mtu.channel_id,
                event->mtu.value
            );

            // Retrieve connection details and handle any errors.
            ret_code = ble_gap_conn_find(event->mtu.conn_handle, &desc);
            if (ret_code == 0)
            {
                // Log connection details
                ble_log_conn(&desc);
            }
            else
            {
                // Log an error if connection descriptor is not found.
                ESP_LOGE(
                    s_tag,
                    "Failed to find connection descriptor for current connection.\n"
                    "\tconn_handle=%d\n"
                    "\tret_code=%d\n",
                    event->mtu.conn_handle,
                    ret_code
                );
            }
            
            // Break from switch statement after handling event.
            break;

        // Handle repeat pairing events by deleting existing bond and retrying pairing.
        case BLE_GAP_EVENT_REPEAT_PAIRING:

            // Log event and repeat pairing details.
            ESP_LOGI(
                s_tag,
                "Repeat pairing event triggered.\n"
            );

            // Retrieve connection details and handle any errors.
            ret_code = ble_gap_conn_find(event->repeat_pairing.conn_handle, &desc);
            if (ret_code == 0)
            {
                // Log connection details
                ble_log_conn(&desc);

                // Delete existing bond for peer to allow pairing to proceed.
                ble_store_util_delete_peer(&desc.peer_id_addr);

                // Set return code to retry pairing after deleting existing bond.
                ret_code = BLE_GAP_REPEAT_PAIRING_RETRY;
            }
            else
            {
                // Log an error if connection descriptor is not found.
                ESP_LOGE(
                    s_tag,
                    "Failed to find connection descriptor for current connection.\n"
                    "\tconn_handle=%d\n"
                    "\tret_code=%d\n",
                    event->repeat_pairing.conn_handle,
                    ret_code
                );
            }

            // Break from switch statement after handling event.
            break;
    }

    // Return zero to indicate successful event handling, or event-specific return codes.
    return ret_code;
}

static void ble_on_reset(int reason)
{
    // Log reset and the reason for the BLE host reset.
    ESP_LOGI(
        s_tag,
        "State reset requested.\n"
        "\treason=%d\n",
        reason
    );
}

static void ble_on_sync(void)
{
    // Define return code variable for error handling.
    int ret_code = 0;

    // Ensure BLE host has a valid address before starting advertising and handle any errors.
    ret_code = ble_hs_util_ensure_addr(0);
    if (ret_code == 0)
    {
        // Automatically determine BLE host address type and handle any errors.
        ret_code = ble_hs_id_infer_auto(0, &own_addr_type);
        if (ret_code == 0)
        {
            // Define a buffer to hold BLE address value.
            uint8_t addr_val[6] = {0};

            // Copy BLE host address value into buffer and handle any errors.
            ret_code = ble_hs_id_copy_addr(own_addr_type, addr_val, NULL);
            if (ret_code == 0)
            {
                // Update BLE address in shared state for display and diagnostics.
                char own_addr[VP_BLE_ADDR_MAX_LEN];
                ble_convert_addr(addr_val, own_addr, sizeof(own_addr));
                vp_state_set_ble_uuid_addr(own_addr);

                // Log the BLE host address.
                ESP_LOGI(
                    s_tag,
                    "Updated BLE host address.\n"
                    "\town_addr_type=%d\n"
                    "\town_addr=%s\n",
                    own_addr_type,
                    own_addr
                );
            }
            else
            {
                // Log an error if the BLE host address cannot be copied.
                ESP_LOGE(
                    s_tag,
                    "Failed to copy BLE host address.\n"
                    "\tret_code=%d\n",
                    ret_code
                );
            }
        }
        else
        {
            // Log an error if the BLE host address type cannot be inferred.
            ESP_LOGE(
                s_tag,
                "Failed to determine BLE host address type.\n"
                "\tret_code=%d\n",
                ret_code
            );
        }
    }
    else
    {
        // Log an error if the BLE host address cannot be ensured.
        ESP_LOGE(
            s_tag,
            "Failed to ensure BLE host address.\n"
            "\tret_code=%d\n",
            ret_code
        );
    }

    // Start advertising to allow connections.
    ble_start_advertising();
}

static void ble_on_gatts_register(struct ble_gatt_register_ctxt *ctxt, void *arg)
{
    // Define a buffer to hold formatted UUID strings.
    char uuid_str[BLE_UUID_STR_LEN];

    // Handle GATT registration operations based on the type of registration.
    switch (ctxt->op) {

        // Handle service registration operations.
        case BLE_GATT_REGISTER_OP_SVC:

            // Log service registration details.
            ESP_LOGI(
                s_tag,
                "Registered service operation.\n"
                "\tuuid=%s\n"
                "\thandle=%d\n",
                ble_uuid_to_str(ctxt->svc.svc_def->uuid, uuid_str),
                ctxt->svc.handle
            );
            
            // Break from switch statement after handling operation.
            break;

        // Handle characteristic registration operations.
        case BLE_GATT_REGISTER_OP_CHR:

            // Log characteristic registration details.
            ESP_LOGI(
                s_tag,
                "Registered characteristic operation.\n"
                "\tuuid=%s\n"
                "\tdef_handle=%d\n"
                "\tval_handle=%d\n",
                ble_uuid_to_str(ctxt->chr.chr_def->uuid, uuid_str),
                ctxt->chr.def_handle,
                ctxt->chr.val_handle
            );

            // Break from switch statement after handling operation.
            break;

        // Handle descriptor registration operations.
        case BLE_GATT_REGISTER_OP_DSC:

            // Log descriptor registration details.
            ESP_LOGI(
                s_tag,
                "Registered descriptor operation.\n"
                "\tuuid=%s\n"
                "\thandle=%d\n",
                ble_uuid_to_str(ctxt->dsc.dsc_def->uuid, uuid_str),
                ctxt->dsc.handle
            );

            // Break from switch statement after handling operation.
            break;

        // Handle unexpected registration operations.
        default:

            // Log an error if an unexpected GATT registration operation is requested.
            ESP_LOGE(
                s_tag,
                "Unexpected registration operation requested\n"
                "\top=%d\n",
                ctxt->op
            );

            // Break from switch statement after handling operation.
            break;
    }
}

static void ble_host_task(void *param)
{
    // Log the start of the BLE host task.
    ESP_LOGI(
        s_tag,
        "BLE host task started\n"
    );

    // Run the BLE host task to process events and manage BLE operations, while blocking until end.
    nimble_port_run();

    // Deinitialize the BLE host task and log its completion.
    nimble_port_freertos_deinit();
}

esp_err_t ble_manager_init(void)
{
    // Define return code and error code variables for error handling.
    int ret_code = 0;
    esp_err_t err_code = ESP_OK;

    // Initialize the NimBLE host stack and handle any errors.
    err_code = nimble_port_init();
    if (err_code == ESP_OK)
    {
        // Set BLE host configuration callbacks.
        ble_hs_cfg.reset_cb = ble_on_reset;
        ble_hs_cfg.sync_cb = ble_on_sync;
        ble_hs_cfg.gatts_register_cb = ble_on_gatts_register;
        ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

        // Configure BLE security parameters for pairing and bonding.
        ble_hs_cfg.sm_io_cap = CONFIG_EXAMPLE_IO_TYPE;
        ble_hs_cfg.sm_sc = 0;

        // Initialize GATT server and handle any errors.
        ret_code = ble_gatt_server_init();
        if (ret_code == 0)
        {
            // Set the device name for the GATT server and handle any errors.
            ret_code = ble_svc_gap_device_name_set("VocalPoint");
            if (ret_code == 0)
            {
                // Initialize BLE storage configuration.
                ble_store_config_init();

                // Start the BLE host task to process BLE events and manage BLE operations.
                nimble_port_freertos_init(ble_host_task);
            }
            else
            {
                // Log an error if the device name for the GATT server cannot be set.
                ESP_LOGI(
                    s_tag,
                    "Failed to set device name for GATT server.\n"
                    "\tret_code=%d\n",
                    ret_code
                );

                // Set error code to indicate failure of BLE manager initialization.
                err_code = ESP_FAIL;
            }
        }
        else
        {
            // Log an error if the GATT server fails to initialize.
            ESP_LOGI(
                s_tag,
                "Failed to initialize GATT server\n"
                "\tret_code=%d\n",
                ret_code
            );

            // Set error code to indicate failure of BLE manager initialization.
            err_code = ESP_FAIL;
        }
    }
    else
    {
        // Log an error if the BLE host stack fails to initialize.
        ESP_LOGI(
            s_tag,
            "Failed to initialize NimBLE.\n"
            "\terr_code=%d\n",
            err_code
        );
    }

    // Return the error code to indicate success or failure of BLE manager initialization.
    return err_code;
}
