/**************************************************************************************************/
/**
 * @file ble_gatt_server.c
 * @brief BLE GATT server implementation for custom control and metadata characteristics.
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
#include <stdio.h>

// Third-party includes
#include "esp_log.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "services/ans/ble_svc_ans.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

// Project includes
#include "ble_gatt_server.h"
#include "log.h"
#include "state.h"


/***************************************************************************************************
 * Variable Declarations
 **************************************************************************************************/

static uint16_t s_batt_chr_handle;
static const size_t s_metadata_text_capacity = 448U;


/***************************************************************************************************
 * Function Definitions
 **************************************************************************************************/

/**************************************************************************************************/
/**
 * @name voice_profile_number_access_cb
 * @brief Handles read access for the voice profile number characteristic.
 *
 * @param conn_handle Active BLE connection handle.
 * @param attr_handle Characteristic attribute handle.
 * @param ctxt GATT access context with request data and output mbuf.
 * @param arg User callback argument (unused).
 *
 * @return int 0 on success, otherwise ATT error code.
 */
/**************************************************************************************************/
static int voice_profile_number_access_cb(
    uint16_t conn_handle,
    uint16_t attr_handle,
    struct ble_gatt_access_ctxt *ctxt,
    void *arg
)
{
    // Define return code variable for error handling.
    int ret_code = BLE_ATT_ERR_UNLIKELY;

    // Verify that the access operation is a characteristic read.
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR)
    {
        // Declare a snapshot structure to hold the latest shared state for response construction.
        vp_state_snapshot_t snapshot;

        // Read the latest shared state and expose the current profile number.
        vp_state_get_snapshot(&snapshot);

        // Append the voice profile number to the response mbuf and handle any errors.
        int ret_code = os_mbuf_append(
            ctxt->om,
            &snapshot.voice_profile_num,
            sizeof(snapshot.voice_profile_num)
        );
        if (ret_code != 0)
        {
            // Log error if appending voice profile number to response mbuf fails.
            ESP_LOGE(
                s_tag,
                "Failed to append voice profile number to response mbuf.\n"
                "\tmbuf_len=%d\n"
                "\tmbuf_flags=0x%02x\n",
                ctxt->om->om_len,
                ctxt->om->om_flags
            );

            // Set return code to indicate insufficient resources for response.
            ret_code = BLE_ATT_ERR_INSUFFICIENT_RES;
        }
        else
        {
            // Log successful read of voice profile number for diagnostics.
            ESP_LOGI(
                s_tag,
                "Voice profile number read request.\n"
                "\tvoice_profile_num=%u\n",
                snapshot.voice_profile_num
            );
        }
    }
    else
    {
        // Log error if unsupported access operation is attempted.
        ESP_LOGE(
            s_tag,
            "Unsupported GATT access operation attempted on voice profile number characteristic.\n"
            "\top=%d\n",
            ctxt->op
        );
    }

    // Return appropriate ATT error code for unsupported operations.
    return ret_code;
}

/**************************************************************************************************/
/**
 * @name volume_access_cb
 * @brief Handles read/write access for the volume characteristic.
 *
 * @param conn_handle Active BLE connection handle.
 * @param attr_handle Characteristic attribute handle.
 * @param ctxt GATT access context with request data and output mbuf.
 * @param arg User callback argument (unused).
 *
 * @return int 0 on success, otherwise ATT error code.
 */
/**************************************************************************************************/
static int volume_access_cb(
    uint16_t conn_handle,
    uint16_t attr_handle,
    struct ble_gatt_access_ctxt *ctxt,
    void *arg
)
{
    // Define return code variable for error handling.
    int ret_code = BLE_ATT_ERR_UNLIKELY;

    // Handle characteristic read requests.
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR)
    {
        // Declare snapshot structure to hold latest shared state for response construction.
        vp_state_snapshot_t snapshot;

        // Read latest shared state and expose current profile number.
        vp_state_get_snapshot(&snapshot);

        // Append volume to response mbuf and handle any errors.
        ret_code = os_mbuf_append(ctxt->om, &snapshot.volume, sizeof(snapshot.volume));
        if (ret_code != 0)
        {
            // Log error if appending volume to response mbuf fails.
            ESP_LOGE(
                s_tag,
                "Failed to append volume to response mbuf.\n"
                "\tmbuf_len=%d\n"
                "\tmbuf_flags=0x%02x\n",
                ctxt->om->om_len,
                ctxt->om->om_flags
            );

            // Set return code to indicate insufficient resources for response.
            ret_code = BLE_ATT_ERR_INSUFFICIENT_RES;
        }
        else
        {
            // Log successful read of volume for diagnostics.
            ESP_LOGI(
                s_tag,
                "Volume read request.\n"
                "\tvolume=%u\n",
                snapshot.volume
            );
        }
    }
    // Handle characteristic write requests.
    else if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR)
    {
        // Define a variable to hold the parsed volume value from the write payload.
        uint8_t value = 0;

        // Parse a single-byte volume payload and apply it to shared state.
        ret_code = ble_hs_mbuf_to_flat(ctxt->om, &value, sizeof(value), NULL);
        if (ret_code == 0)
        {
            // Update shared state with the new volume value, ensuring it does not exceed 100%.
            vp_state_set_volume(value);

            // Log the updated volume value for diagnostics.
            ESP_LOGI(
                s_tag,
                "Volume write request.\n"
                "\tvolume=%u\n",
                value
            );
        }
        else
        {
            // Log an error if the write payload cannot be parsed.
            ESP_LOGE(
                s_tag,
                "Failed to parse volume write payload.\n"
                "\tret_code=%d\n",
                ret_code
            );

            // Map transport parse error to ATT unlikely error.
            ret_code = BLE_ATT_ERR_UNLIKELY;
        }
    }
    else
    {
        // Log an error if an unsupported access operation is attempted.
        ESP_LOGE(
            s_tag,
            "Unsupported GATT access operation attempted on volume characteristic.\n"
            "\top=%d\n",
            ctxt->op
        );
    }

    // Return the appropriate ATT status code for the requested operation.
    return ret_code;
}

/**************************************************************************************************/
/**
 * @name metadata_access_cb
 * @brief Handles read/write access for metadata payload exchange.
 *
 * @param conn_handle Active BLE connection handle.
 * @param attr_handle Characteristic attribute handle.
 * @param ctxt GATT access context with request data and output mbuf.
 * @param arg User callback argument (unused).
 *
 * @return int 0 on success, otherwise ATT error code.
 */
/**************************************************************************************************/
static int metadata_access_cb(
    uint16_t conn_handle,
    uint16_t attr_handle,
    struct ble_gatt_access_ctxt *ctxt,
    void *arg
)
{
    // Define return code variable for error handling.
    int ret_code = BLE_ATT_ERR_UNLIKELY;

    // Handle characteristic read requests.
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR)
    {
        // Declare snapshot structure to hold latest shared state for response construction.
        vp_state_snapshot_t snapshot;

        // Read latest shared state and expose current profile number.
        vp_state_get_snapshot(&snapshot);

        // Define a buffer to hold formatted metadata string.
        char text[s_metadata_text_capacity];

        // Format shared state into a delimited key-value string for transmission in mbuf.
        int len = snprintf(
            text,
            sizeof(text),
            "BLE_UUID_ADDR=%s;"
            "VOICE_PROFILE_NUM=%u;"
            "VOICE_PROFILE_NAME=%s;"
            "VOICE_PROFILE_NAME_NUM=%u;"
            "AUDIO_OUT_NAME_SEND=%s;"
            "AUDIO_OUT_NAME_SET=%s;"
            "AUDIO_OUT_NAME=%s;"
            "WIFI_SSID=%s;"
            "WIFI_PWD=%s",
            snapshot.ble_uuid_addr,
            snapshot.voice_profile_num,
            snapshot.voice_profile_name,
            snapshot.voice_profile_name_num,
            snapshot.audio_out_name_send,
            snapshot.audio_out_name_set,
            snapshot.audio_out_name_set,
            snapshot.wifi_ssid,
            snapshot.wifi_pwd);
        
        // Verify that metadata string was formatted successfully and handle any errors.
        if (len < 0)
        {
            // Log error if metadata payload formatting fails.
            ESP_LOGE(
                s_tag,
                "Failed to format metadata payload for read response.\n"
                "\tlen=%d\n",
                len
            );

            // Set return code to indicate an unlikely error during response preparation.
            ret_code = BLE_ATT_ERR_UNLIKELY;
        }
        else
        {
            // Ensure that formatted metadata string does not exceed defined capacity.
            if ((size_t)len >= s_metadata_text_capacity)
            {
                len = (int)s_metadata_text_capacity - 1;
            }

            // Append formatted metadata string to response mbuf and handle any errors.
            ret_code = os_mbuf_append(ctxt->om, text, (uint16_t)len);
            if (ret_code != 0)
            {
                // Log error if appending metadata payload to response mbuf fails.
                ESP_LOGE(
                    s_tag,
                    "Failed to append metadata payload to response mbuf.\n"
                    "\tmbuf_len=%d\n"
                    "\tmbuf_flags=0x%02x\n",
                    ctxt->om->om_len,
                    ctxt->om->om_flags
                );

                // Set return code to indicate insufficient resources for response.
                ret_code = BLE_ATT_ERR_INSUFFICIENT_RES;
            }
            else
            {
                // Log successful read of metadata for diagnostics.
                ESP_LOGI(
                    s_tag,
                    "Metadata read request.\n"
                    "\tmetadata=%s\n",
                    text
                );
            }
        }
    }
    // Handle characteristic write requests.
    else if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        // Declare buffer to hold raw metadata payload from write request.
        uint8_t payload[128];

        // Define variable to hold length of parsed payload.
        uint16_t copied = 0;

        // Parse the write payload into a flat buffer and handle any errors.
        ret_code = ble_hs_mbuf_to_flat(ctxt->om, payload, sizeof(payload), &copied);
        if (ret_code != 0) {
            // Log error if write payload cannot be parsed.
            ESP_LOGE(
                s_tag,
                "Failed to parse metadata write payload.\n"
                "\tret_code=%d\n",
                ret_code
            );

            // Set return code to indicate an unlikely error during payload parsing.
            ret_code = BLE_ATT_ERR_UNLIKELY;
        } else {
            // Update shared state based on the parsed metadata payload.
            vp_state_update_from_ble_payload(payload, copied);

            // Log the received metadata payload for diagnostics.
            ESP_LOGI(
                s_tag,
                "Metadata write request.\n"
                "\tpayload_len=%u\n"
                "\tpayload=%.*s\n",
                copied,
                copied,
                payload
            );
        }
    }
    else {
        // Log error if unsupported access operation is attempted.
        ESP_LOGE(
            s_tag,
            "Unsupported GATT access operation attempted on metadata characteristic.\n"
            "\top=%d\n",
            ctxt->op
        );
    }

    // Return the appropriate ATT status code for the requested operation.
    return ret_code;
}

/**************************************************************************************************/
/**
 * @name s_gatt_services
 * @brief Custom GATT service table containing control and voice profile services.
 *
 * @return Array of GATT service definitions, terminated by an empty entry.
 */
/**************************************************************************************************/
static const struct ble_gatt_svc_def s_gatt_services[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0xFFFF),
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = BLE_UUID16_DECLARE(0xFF01),
                .access_cb = volume_access_cb,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_WRITE,
            },
            {
                .uuid = BLE_UUID16_DECLARE(0xFF02),
                .access_cb = metadata_access_cb,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_WRITE,
            },
            {0},
        },
    },
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0x180F),
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = BLE_UUID16_DECLARE(0x2A19),
                .access_cb = voice_profile_number_access_cb,
                .val_handle = &s_batt_chr_handle,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
            },
            {0},
        },
    },
    {0},
};

/**************************************************************************************************/
/**
 * @name ble_gatt_server_init
 * @brief Initializes standard BLE services and registers custom service definitions.
 *
 * @return int 0 on success, non-zero NimBLE error code on failure.
 */
/**************************************************************************************************/
int ble_gatt_server_init(void)
{
    // Define return code variable for error handling.
    int ret_code = 0;

    // Initialize standard BLE services.
    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_svc_ans_init();

    // Register custom GATT service definitions and handle any errors.
    ret_code = ble_gatts_count_cfg(s_gatt_services);
    if (ret_code == 0)
    {
        // Register the GATT services and handle any errors.
        ret_code = ble_gatts_add_svcs(s_gatt_services);
        if (ret_code != 0)
        {
            // Log error if registering GATT services fails.
            ESP_LOGE(
                s_tag,
                "Failed to register GATT services.\n"
                "\tret_code=%d\n",
                ret_code
            );
        }
    }
    else
    {
        // Log error if registering GATT services fails.
        ESP_LOGE(
            s_tag,
            "Failed to register GATT services.\n"
            "\tret_code=%d\n",
            ret_code
        );
    }

    // Return 0 on success, or the appropriate NimBLE error code on failure.
    return ret_code;
}
