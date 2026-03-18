/**************************************************************************************************/
/**
 * @file ble_gatt_server.c
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

#include "ble_gatt_server.h"

#include <assert.h>
#include <stdio.h>

#include "esp_log.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "state.h"
#include "services/ans/ble_svc_ans.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

static const char *s_tag = "ble_gatt_server";
static uint16_t s_batt_chr_handle;
static const size_t s_metadata_text_capacity = 448U;

static int voice_profile_number_access_cb(uint16_t conn_handle,
                                          uint16_t attr_handle,
                                          struct ble_gatt_access_ctxt *ctxt,
                                          void *arg)
{
    (void)conn_handle;
    (void)attr_handle;
    (void)arg;

    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        vp_state_snapshot_t snapshot;
        vp_state_get_snapshot(&snapshot);

        int rc = os_mbuf_append(ctxt->om,
                                &snapshot.voice_profile_num,
                                sizeof(snapshot.voice_profile_num));
        return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
    }

    return BLE_ATT_ERR_UNLIKELY;
}

static int volume_access_cb(uint16_t conn_handle,
                            uint16_t attr_handle,
                            struct ble_gatt_access_ctxt *ctxt,
                            void *arg)
{
    (void)conn_handle;
    (void)attr_handle;
    (void)arg;

    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        vp_state_snapshot_t snapshot;
        vp_state_get_snapshot(&snapshot);

        int rc = os_mbuf_append(ctxt->om, &snapshot.volume, sizeof(snapshot.volume));
        return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
    }

    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        uint8_t value = 0;
        int rc = ble_hs_mbuf_to_flat(ctxt->om, &value, sizeof(value), NULL);
        if (rc != 0) {
            return BLE_ATT_ERR_UNLIKELY;
        }

        vp_state_set_volume(value);
        ESP_LOGI(s_tag, "Volume set to %u", value > 100 ? 100 : value);
        return 0;
    }

    return BLE_ATT_ERR_UNLIKELY;
}

static int metadata_access_cb(uint16_t conn_handle,
                              uint16_t attr_handle,
                              struct ble_gatt_access_ctxt *ctxt,
                              void *arg)
{
    (void)conn_handle;
    (void)attr_handle;
    (void)arg;

    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        vp_state_snapshot_t snapshot;
        vp_state_get_snapshot(&snapshot);

        char text[448];
        int len = snprintf(text,
                           sizeof(text),
                           "BLE_UUID_ADDR=%s;VOICE_PROFILE_NUM=%u;VOICE_PROFILE_NAME=%s;"
                           "VOICE_PROFILE_NAME_NUM=%u;AUDIO_OUT_NAME_SEND=%s;"
                           "AUDIO_OUT_NAME_SET=%s;AUDIO_OUT_NAME=%s;WIFI_SSID=%s;WIFI_PWD=%s",
                           snapshot.ble_uuid_addr,
                           snapshot.voice_profile_num,
                           snapshot.voice_profile_name,
                           snapshot.voice_profile_name_num,
                           snapshot.audio_out_name_send,
                           snapshot.audio_out_name_set,
                           snapshot.audio_out_name_set,
                           snapshot.wifi_ssid,
                           snapshot.wifi_pwd);
        if (len < 0) {
            return BLE_ATT_ERR_UNLIKELY;
        }

        if ((size_t)len >= s_metadata_text_capacity) {
            len = (int)s_metadata_text_capacity - 1;
        }

        int rc = os_mbuf_append(ctxt->om, text, (uint16_t)len);
        return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
    }

    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        uint8_t payload[128];
        uint16_t copied = 0;
        int rc = ble_hs_mbuf_to_flat(ctxt->om, payload, sizeof(payload), &copied);
        if (rc != 0) {
            return BLE_ATT_ERR_UNLIKELY;
        }

        vp_state_update_from_ble_payload(payload, copied);
        return 0;
    }

    return BLE_ATT_ERR_UNLIKELY;
}

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

void ble_gatt_server_notify_voice_profile_number(uint16_t conn_handle)
{
    if (conn_handle == BLE_HS_CONN_HANDLE_NONE) {
        return;
    }

    vp_state_snapshot_t snapshot;
    vp_state_get_snapshot(&snapshot);

    struct os_mbuf *om = ble_hs_mbuf_from_flat(&snapshot.voice_profile_num,
                                               sizeof(snapshot.voice_profile_num));
    if (om == NULL) {
        return;
    }

    ble_gatts_notify_custom(conn_handle, s_batt_chr_handle, om);
}

void ble_gatt_server_set_voice_profile_number(uint8_t voice_profile_number)
{
    vp_state_set_voice_profile_number(voice_profile_number);
}

void ble_gatt_server_register_cb(struct ble_gatt_register_ctxt *ctxt, void *arg)
{
    (void)arg;

    char uuid_str[BLE_UUID_STR_LEN];

    switch (ctxt->op) {
        case BLE_GATT_REGISTER_OP_SVC:
            MODLOG_DFLT(DEBUG,
                        "registered service %s with handle=%d\n",
                        ble_uuid_to_str(ctxt->svc.svc_def->uuid, uuid_str),
                        ctxt->svc.handle);
            break;

        case BLE_GATT_REGISTER_OP_CHR:
            MODLOG_DFLT(DEBUG,
                        "registering characteristic %s with def_handle=%d val_handle=%d\n",
                        ble_uuid_to_str(ctxt->chr.chr_def->uuid, uuid_str),
                        ctxt->chr.def_handle,
                        ctxt->chr.val_handle);
            break;

        case BLE_GATT_REGISTER_OP_DSC:
            MODLOG_DFLT(DEBUG,
                        "registering descriptor %s with handle=%d\n",
                        ble_uuid_to_str(ctxt->dsc.dsc_def->uuid, uuid_str),
                        ctxt->dsc.handle);
            break;

        default:
            assert(0);
            break;
    }
}

int ble_gatt_server_init(void)
{
    int rc;

    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_svc_ans_init();

    rc = ble_gatts_count_cfg(s_gatt_services);
    if (rc != 0) {
        return rc;
    }

    rc = ble_gatts_add_svcs(s_gatt_services);
    if (rc != 0) {
        return rc;
    }

    return 0;
}
