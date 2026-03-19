/**************************************************************************************************/
/**
 * @file state.c
 * @brief Shared BLE/I2C application state.
 *
 * @version 0.1
 * @date 2026-03-18
 */
/**************************************************************************************************/

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "configs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "i2c_protocol.h"
#include "state.h"

typedef struct {
    uint32_t seq;
    uint8_t volume;
    uint8_t voice_profile_num;
    char ble_uuid_addr[VP_BLE_ADDR_MAX_LEN];
    char audio_out_name_send[VP_PARAM_MAX_LEN];
    char audio_out_name_set[VP_PARAM_MAX_LEN];
    char wifi_ssid[VP_PARAM_MAX_LEN];
    char wifi_pwd[VP_PARAM_MAX_LEN];
    char audio_out_disconnect_name[VP_PARAM_MAX_LEN];
    char audio_out_forget_name[VP_PARAM_MAX_LEN];
    uint8_t voice_profile_name_num;
    char voice_profile_name[VP_VOICE_PROFILE_NAME_MAX_LEN];
    char voice_profile_catalog[VP_MAX_VOICE_PROFILES][VP_VOICE_PROFILE_NAME_MAX_LEN];
    uint8_t voice_profile_catalog_count;
} vp_state_t;

static SemaphoreHandle_t s_state_mutex;
static vp_state_t s_state;
static uint8_t s_cached_frame[VP_I2C_FRAME_SIZE];
static uint32_t s_dirty_flags;

static uint8_t clamp_pct(uint8_t value)
{
    return (value > 100U) ? 100U : value;
}

static void copy_string(char *dst, size_t dst_size, const char *src)
{
    if (dst_size == 0U) {
        return;
    }

    if (src == NULL) {
        dst[0] = '\0';
        return;
    }

    strncpy(dst, src, dst_size - 1U);
    dst[dst_size - 1U] = '\0';
}

static int strings_equal(const char *lhs, const char *rhs)
{
    if (lhs == NULL || rhs == NULL) {
        return lhs == rhs;
    }

    return strcmp(lhs, rhs) == 0;
}

static int key_equals(const char *lhs, const char *rhs)
{
    while (*lhs != '\0' && *rhs != '\0') {
        if (toupper((unsigned char)*lhs) != toupper((unsigned char)*rhs)) {
            return 0;
        }

        lhs++;
        rhs++;
    }

    return (*lhs == '\0' && *rhs == '\0');
}

static int value_is_truthy(const char *value)
{
    if (value == NULL) {
        return 0;
    }

    return strcmp(value, "1") == 0 ||
           strcmp(value, "true") == 0 ||
           strcmp(value, "TRUE") == 0 ||
           strcmp(value, "yes") == 0 ||
           strcmp(value, "YES") == 0 ||
           strcmp(value, "on") == 0 ||
           strcmp(value, "ON") == 0;
}

static void lock_state(void)
{
    if (s_state_mutex != NULL) {
        xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    }
}

static void unlock_state(void)
{
    if (s_state_mutex != NULL) {
        xSemaphoreGive(s_state_mutex);
    }
}

static uint16_t crc16_ccitt(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFU;

    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;

        for (uint8_t bit = 0; bit < 8U; bit++) {
            if ((crc & 0x8000U) != 0U) {
                crc = (uint16_t)((crc << 1) ^ 0x1021U);
            } else {
                crc <<= 1;
            }
        }
    }

    return crc;
}

static void rebuild_cached_frame_locked(void)
{
    size_t offset = 0U;

    memset(s_cached_frame, 0, sizeof(s_cached_frame));

    s_cached_frame[offset++] = VP_FRAME_MAGIC;
    s_cached_frame[offset++] = VP_FRAME_VERSION;

    s_cached_frame[offset++] = (uint8_t)(s_state.seq & 0xFFU);
    s_cached_frame[offset++] = (uint8_t)((s_state.seq >> 8) & 0xFFU);
    s_cached_frame[offset++] = (uint8_t)((s_state.seq >> 16) & 0xFFU);
    s_cached_frame[offset++] = (uint8_t)((s_state.seq >> 24) & 0xFFU);

    s_cached_frame[offset++] = s_state.volume;
    s_cached_frame[offset++] = s_state.voice_profile_num;

    memcpy(&s_cached_frame[offset], s_state.ble_uuid_addr, sizeof(s_state.ble_uuid_addr));
    offset += sizeof(s_state.ble_uuid_addr);

    memcpy(&s_cached_frame[offset], s_state.audio_out_name_send, sizeof(s_state.audio_out_name_send));
    offset += sizeof(s_state.audio_out_name_send);

    memcpy(&s_cached_frame[offset], s_state.audio_out_name_set, sizeof(s_state.audio_out_name_set));
    offset += sizeof(s_state.audio_out_name_set);

    memcpy(&s_cached_frame[offset], s_state.wifi_ssid, sizeof(s_state.wifi_ssid));
    offset += sizeof(s_state.wifi_ssid);

    memcpy(&s_cached_frame[offset], s_state.wifi_pwd, sizeof(s_state.wifi_pwd));
    offset += sizeof(s_state.wifi_pwd);

    memcpy(&s_cached_frame[offset],
           s_state.audio_out_disconnect_name,
           sizeof(s_state.audio_out_disconnect_name));
    offset += sizeof(s_state.audio_out_disconnect_name);

    memcpy(&s_cached_frame[offset],
           s_state.audio_out_forget_name,
           sizeof(s_state.audio_out_forget_name));
    offset += sizeof(s_state.audio_out_forget_name);

    s_cached_frame[offset++] = s_state.voice_profile_name_num;

    memcpy(&s_cached_frame[offset], s_state.voice_profile_name, sizeof(s_state.voice_profile_name));

    uint16_t crc = crc16_ccitt(s_cached_frame, VP_I2C_FRAME_SIZE - 2U);
    s_cached_frame[VP_I2C_FRAME_SIZE - 2U] = (uint8_t)(crc & 0xFFU);
    s_cached_frame[VP_I2C_FRAME_SIZE - 1U] = (uint8_t)((crc >> 8) & 0xFFU);
}

static void commit_state_update_locked(uint32_t dirty_mask)
{
    s_state.seq++;
    s_dirty_flags |= VP_FLAG_CHANGED | dirty_mask;
    s_dirty_flags &= VP_STATUS_BITS_MASK;
    rebuild_cached_frame_locked();
}

static int set_volume_locked(uint8_t volume)
{
    uint8_t next = clamp_pct(volume);

    if (s_state.volume == next) {
        return 0;
    }

    s_state.volume = next;
    return 1;
}

static int set_voice_profile_number_locked(uint8_t voice_profile_number)
{
    uint8_t next = clamp_pct(voice_profile_number);

    if (s_state.voice_profile_num == next) {
        return 0;
    }

    s_state.voice_profile_num = next;
    return 1;
}

static int set_ble_uuid_addr_locked(const char *addr)
{
    char next[VP_BLE_ADDR_MAX_LEN];

    copy_string(next, sizeof(next), addr);
    if (strings_equal(s_state.ble_uuid_addr, next)) {
        return 0;
    }

    copy_string(s_state.ble_uuid_addr, sizeof(s_state.ble_uuid_addr), next);
    return 1;
}

static int set_audio_out_name_send_locked(const char *value)
{
    char next[VP_PARAM_MAX_LEN];

    copy_string(next, sizeof(next), value);
    if (strings_equal(s_state.audio_out_name_send, next)) {
        return 0;
    }

    copy_string(s_state.audio_out_name_send, sizeof(s_state.audio_out_name_send), next);
    return 1;
}

static int set_audio_out_name_set_locked(const char *value)
{
    char next[VP_PARAM_MAX_LEN];

    copy_string(next, sizeof(next), value);
    if (strings_equal(s_state.audio_out_name_set, next)) {
        return 0;
    }

    copy_string(s_state.audio_out_name_set, sizeof(s_state.audio_out_name_set), next);
    return 1;
}

static int set_wifi_ssid_locked(const char *value)
{
    char next[VP_PARAM_MAX_LEN];

    copy_string(next, sizeof(next), value);
    if (strings_equal(s_state.wifi_ssid, next)) {
        return 0;
    }

    copy_string(s_state.wifi_ssid, sizeof(s_state.wifi_ssid), next);
    return 1;
}

static int set_wifi_pwd_locked(const char *value)
{
    char next[VP_PARAM_MAX_LEN];

    copy_string(next, sizeof(next), value);
    if (strings_equal(s_state.wifi_pwd, next)) {
        return 0;
    }

    copy_string(s_state.wifi_pwd, sizeof(s_state.wifi_pwd), next);
    return 1;
}

static int queue_audio_out_disconnect_name_locked(const char *value)
{
    char next[VP_PARAM_MAX_LEN];

    copy_string(next, sizeof(next), value);
    if (next[0] == '\0') {
        return 0;
    }

    copy_string(s_state.audio_out_disconnect_name, sizeof(s_state.audio_out_disconnect_name), next);
    return 1;
}

static int queue_audio_out_forget_name_locked(const char *value)
{
    char next[VP_PARAM_MAX_LEN];

    copy_string(next, sizeof(next), value);
    if (next[0] == '\0') {
        return 0;
    }

    copy_string(s_state.audio_out_forget_name, sizeof(s_state.audio_out_forget_name), next);
    return 1;
}

static int register_voice_profile_name_locked(const char *value)
{
    char next[VP_VOICE_PROFILE_NAME_MAX_LEN];
    uint8_t profile_num = 0U;
    int found = 0;
    int changed = 0;

    copy_string(next, sizeof(next), value);
    if (next[0] == '\0') {
        return 0;
    }

    for (uint8_t i = 0; i < s_state.voice_profile_catalog_count; i++) {
        if (strings_equal(s_state.voice_profile_catalog[i], next)) {
            profile_num = i;
            found = 1;
            break;
        }
    }

    if (!found) {
        if (s_state.voice_profile_catalog_count < VP_MAX_VOICE_PROFILES) {
            profile_num = s_state.voice_profile_catalog_count;
            copy_string(s_state.voice_profile_catalog[profile_num],
                        sizeof(s_state.voice_profile_catalog[profile_num]),
                        next);
            s_state.voice_profile_catalog_count++;
        } else {
            profile_num = (uint8_t)(VP_MAX_VOICE_PROFILES - 1U);
            copy_string(s_state.voice_profile_catalog[profile_num],
                        sizeof(s_state.voice_profile_catalog[profile_num]),
                        next);
        }
        changed = 1;
    }

    if (!strings_equal(s_state.voice_profile_name, next)) {
        copy_string(s_state.voice_profile_name, sizeof(s_state.voice_profile_name), next);
        changed = 1;
    }

    if (s_state.voice_profile_name_num != profile_num) {
        s_state.voice_profile_name_num = profile_num;
        changed = 1;
    }

    return changed;
}

static int parse_and_apply_token_locked(char *token, uint32_t *dirty_mask)
{
    while (isspace((unsigned char)*token)) {
        token++;
    }

    char *end = token + strlen(token);
    while (end > token && isspace((unsigned char)*(end - 1))) {
        *(--end) = '\0';
    }

    if (token[0] == '\0') {
        return 0;
    }

    char *separator = strchr(token, '=');
    if (separator == NULL) {
        if (set_audio_out_name_set_locked(token)) {
            *dirty_mask |= VP_FLAG_AUDIO_OUT_NAME;
            return 1;
        }
        return 0;
    }

    *separator = '\0';
    char *key = token;
    char *value = separator + 1;

    while (isspace((unsigned char)*key)) {
        key++;
    }
    while (isspace((unsigned char)*value)) {
        value++;
    }

    char *key_end = key + strlen(key);
    while (key_end > key && isspace((unsigned char)*(key_end - 1))) {
        *(--key_end) = '\0';
    }

    if (key_equals(key, "VOL") || key_equals(key, "VOLUME")) {
        long parsed = strtol(value, NULL, 10);
        if (parsed < 0L) {
            parsed = 0L;
        }
        if (parsed > 100L) {
            parsed = 100L;
        }
        if (set_volume_locked((uint8_t)parsed)) {
            *dirty_mask |= VP_FLAG_VOL;
            return 1;
        }
        return 0;
    }

    if (key_equals(key, "VOICE_PROFILE_NUM") || key_equals(key, "VOICE_NUM") ||
        key_equals(key, "VOICE_PROFILE_NUMBER")) {
        long parsed = strtol(value, NULL, 10);
        if (parsed < 0L) {
            parsed = 0L;
        }
        if (parsed > 100L) {
            parsed = 100L;
        }
        if (set_voice_profile_number_locked((uint8_t)parsed)) {
            *dirty_mask |= VP_FLAG_VOICE_PROFILE_NUM;
            return 1;
        }
        return 0;
    }

    if (key_equals(key, "BLE_UUID_ADDR") || key_equals(key, "BLE_ADDR") || key_equals(key, "ADDR")) {
        if (set_ble_uuid_addr_locked(value)) {
            rebuild_cached_frame_locked();
        }
        return 0;
    }

    if (key_equals(key, "AUDIO_OUT_NAME_SEND") || key_equals(key, "AUDIO_OUT_SEND")) {
        if (set_audio_out_name_send_locked(value)) {
            rebuild_cached_frame_locked();
        }
        return 0;
    }

    if (key_equals(key, "AUDIO_OUT_NAME_SET") || key_equals(key, "AUDIO_OUT_NAME") ||
        key_equals(key, "AUDIO_OUT") ||
        key_equals(key, "P1") || key_equals(key, "PARAM1")) {
        if (set_audio_out_name_set_locked(value)) {
            *dirty_mask |= VP_FLAG_AUDIO_OUT_NAME;
            return 1;
        }
        return 0;
    }

    if (key_equals(key, "WIFI_SSID") || key_equals(key, "SSID")) {
        if (set_wifi_ssid_locked(value)) {
            *dirty_mask |= VP_FLAG_WIFI_SSID;
            return 1;
        }
        return 0;
    }

    if (key_equals(key, "WIFI_PWD") || key_equals(key, "WIFI_PASSWORD")) {
        if (set_wifi_pwd_locked(value)) {
            *dirty_mask |= VP_FLAG_WIFI_PWD;
            return 1;
        }
        return 0;
    }

    if (key_equals(key, "AUDIO_OUT_DISCONNECT")) {
        if (queue_audio_out_disconnect_name_locked(value)) {
            *dirty_mask |= VP_FLAG_AUDIO_OUT_DISCONNECT;
            return 1;
        }
        return 0;
    }

    if (key_equals(key, "AUDIO_OUT_FORGET")) {
        if (queue_audio_out_forget_name_locked(value)) {
            *dirty_mask |= VP_FLAG_AUDIO_OUT_FORGET;
            return 1;
        }
        return 0;
    }

    if (key_equals(key, "VOICE_PROFILE_NAME") || key_equals(key, "VOICE_PROFILE") ||
        key_equals(key, "VOICE")) {
        if (register_voice_profile_name_locked(value)) {
            rebuild_cached_frame_locked();
        }
        return 0;
    }

    if (key_equals(key, "REBOOT") || key_equals(key, "RESTART")) {
        if (value_is_truthy(value) && (s_dirty_flags & VP_FLAG_REBOOT) == 0U) {
            *dirty_mask |= VP_FLAG_REBOOT;
            return 1;
        }
        return 0;
    }

    return 0;
}

void vp_state_init(void)
{
    if (s_state_mutex == NULL) {
        s_state_mutex = xSemaphoreCreateMutex();
    }

    lock_state();
    memset(&s_state, 0, sizeof(s_state));
    memset(s_cached_frame, 0, sizeof(s_cached_frame));
    s_dirty_flags = 0U;

#if I2C_TESTING_MODE
    (void)set_volume_locked(2U);
    (void)set_voice_profile_number_locked(0U);
    (void)set_ble_uuid_addr_locked("AA:BB:CC:DD:EE:FF");
    (void)set_audio_out_name_send_locked("Test Output");
    (void)set_audio_out_name_set_locked("Test Output");
    (void)set_wifi_ssid_locked("Test SSID");
    (void)set_wifi_pwd_locked("Test Password");
    (void)queue_audio_out_disconnect_name_locked("");
    (void)queue_audio_out_forget_name_locked("");
    (void)register_voice_profile_name_locked("Test Voice");
    commit_state_update_locked(VP_FLAG_VOL | VP_FLAG_VOICE_PROFILE_NUM |
                               VP_FLAG_AUDIO_OUT_NAME | VP_FLAG_WIFI_SSID | VP_FLAG_WIFI_PWD);
#else
    (void)set_volume_locked(50U);
    (void)set_voice_profile_number_locked(0U);
    (void)set_ble_uuid_addr_locked("N/A");
    (void)set_audio_out_name_send_locked("");
    (void)set_audio_out_name_set_locked("");
    (void)set_wifi_ssid_locked("");
    (void)set_wifi_pwd_locked("");
    (void)queue_audio_out_disconnect_name_locked("");
    (void)queue_audio_out_forget_name_locked("");
    (void)register_voice_profile_name_locked("");
    commit_state_update_locked(VP_FLAG_VOL | VP_FLAG_VOICE_PROFILE_NUM |
                               VP_FLAG_AUDIO_OUT_NAME | VP_FLAG_WIFI_SSID | VP_FLAG_WIFI_PWD);
#endif

    unlock_state();
}

void vp_state_set_volume(uint8_t volume)
{
    lock_state();
    if (set_volume_locked(volume)) {
        commit_state_update_locked(VP_FLAG_VOL);
    }
    unlock_state();
}

void vp_state_set_voice_profile_number(uint8_t voice_profile_number)
{
    lock_state();
    if (set_voice_profile_number_locked(voice_profile_number)) {
        commit_state_update_locked(VP_FLAG_VOICE_PROFILE_NUM);
    }
    unlock_state();
}

void vp_state_set_ble_uuid_addr(const char *addr)
{
    lock_state();
    if (set_ble_uuid_addr_locked(addr)) {
        rebuild_cached_frame_locked();
    }
    unlock_state();
}

void vp_state_set_audio_out_name(const char *value)
{
    lock_state();
    if (set_audio_out_name_set_locked(value)) {
        commit_state_update_locked(VP_FLAG_AUDIO_OUT_NAME);
    }
    unlock_state();
}

void vp_state_announce_audio_out_name(const char *value)
{
    lock_state();
    if (set_audio_out_name_send_locked(value)) {
        rebuild_cached_frame_locked();
    }
    unlock_state();
}

void vp_state_set_wifi_ssid(const char *value)
{
    lock_state();
    if (set_wifi_ssid_locked(value)) {
        commit_state_update_locked(VP_FLAG_WIFI_SSID);
    }
    unlock_state();
}

void vp_state_set_wifi_pwd(const char *value)
{
    lock_state();
    if (set_wifi_pwd_locked(value)) {
        commit_state_update_locked(VP_FLAG_WIFI_PWD);
    }
    unlock_state();
}

void vp_state_register_voice_profile_name(const char *value)
{
    lock_state();
    if (register_voice_profile_name_locked(value)) {
        rebuild_cached_frame_locked();
    }
    unlock_state();
}

void vp_state_get_snapshot(vp_state_snapshot_t *out)
{
    if (out == NULL) {
        return;
    }

    lock_state();
    out->seq = s_state.seq;
    out->volume = s_state.volume;
    out->voice_profile_num = s_state.voice_profile_num;
    copy_string(out->ble_uuid_addr, sizeof(out->ble_uuid_addr), s_state.ble_uuid_addr);
    copy_string(out->audio_out_name_send,
                sizeof(out->audio_out_name_send),
                s_state.audio_out_name_send);
    copy_string(out->audio_out_name_set,
                sizeof(out->audio_out_name_set),
                s_state.audio_out_name_set);
    copy_string(out->wifi_ssid, sizeof(out->wifi_ssid), s_state.wifi_ssid);
    copy_string(out->wifi_pwd, sizeof(out->wifi_pwd), s_state.wifi_pwd);
    copy_string(out->audio_out_disconnect_name,
                sizeof(out->audio_out_disconnect_name),
                s_state.audio_out_disconnect_name);
    copy_string(out->audio_out_forget_name,
                sizeof(out->audio_out_forget_name),
                s_state.audio_out_forget_name);
    out->voice_profile_name_num = s_state.voice_profile_name_num;
    copy_string(out->voice_profile_name,
                sizeof(out->voice_profile_name),
                s_state.voice_profile_name);
    unlock_state();
}

size_t vp_state_build_i2c_frame(uint8_t *out, size_t out_len)
{
    if (out == NULL || out_len < VP_I2C_FRAME_SIZE) {
        return 0;
    }

    lock_state();
    memcpy(out, s_cached_frame, VP_I2C_FRAME_SIZE);
    unlock_state();

    return VP_I2C_FRAME_SIZE;
}

void vp_state_update_from_ble_payload(const uint8_t *payload, uint16_t payload_len)
{
    if (payload == NULL || payload_len == 0U) {
        return;
    }

    char buffer[192];
    size_t copy_len = payload_len;
    uint32_t dirty_mask = 0U;
    int changed = 0;

    if (copy_len >= sizeof(buffer)) {
        copy_len = sizeof(buffer) - 1U;
    }

    memcpy(buffer, payload, copy_len);
    buffer[copy_len] = '\0';

    lock_state();

    char *saveptr = NULL;
    char *token = strtok_r(buffer, ";,", &saveptr);
    while (token != NULL) {
        if (parse_and_apply_token_locked(token, &dirty_mask)) {
            changed = 1;
        }
        token = strtok_r(NULL, ";,", &saveptr);
    }

    if (changed) {
        commit_state_update_locked(dirty_mask);
    }

    unlock_state();
}

uint32_t vp_state_get_dirty_flags(void)
{
    uint32_t flags;

    lock_state();
    flags = s_dirty_flags & VP_STATUS_BITS_MASK;
    unlock_state();
    return flags;
}

void vp_state_clear_dirty_bits(uint32_t mask)
{
    lock_state();
    s_dirty_flags &= ~(mask & VP_STATUS_BITS_MASK);
    s_dirty_flags &= VP_STATUS_BITS_MASK;

    if ((s_dirty_flags & (VP_STATUS_BITS_MASK & ~VP_FLAG_CHANGED)) == 0U) {
        s_dirty_flags &= ~VP_FLAG_CHANGED;
    }
    unlock_state();
}

void vp_state_testing_tick(void)
{
#if I2C_TESTING_MODE
    static uint8_t next_volume = 2U;
    static uint8_t next_voice_profile_num = 0U;
    static uint32_t tick_count = 0U;
    char audio_out_name[VP_PARAM_MAX_LEN];
    char wifi_ssid[VP_PARAM_MAX_LEN];
    char voice_name[VP_VOICE_PROFILE_NAME_MAX_LEN];

    lock_state();

    next_volume = (uint8_t)((next_volume + 3U) % 101U);
    next_voice_profile_num = (uint8_t)((next_voice_profile_num + 1U) % 5U);

    (void)set_volume_locked(next_volume);
    (void)set_voice_profile_number_locked(next_voice_profile_num);
    (void)set_ble_uuid_addr_locked("AA:BB:CC:DD:EE:FF");
    snprintf(audio_out_name, sizeof(audio_out_name), "Output %lu", (unsigned long)tick_count);
    snprintf(wifi_ssid, sizeof(wifi_ssid), "SSID%lu", (unsigned long)tick_count);
    snprintf(voice_name, sizeof(voice_name), "Voice%lu", (unsigned long)tick_count);
    (void)set_audio_out_name_send_locked(audio_out_name);
    (void)set_audio_out_name_set_locked(audio_out_name);
    (void)set_wifi_ssid_locked(wifi_ssid);
    (void)set_wifi_pwd_locked("TestPassword");
    (void)queue_audio_out_disconnect_name_locked("");
    (void)queue_audio_out_forget_name_locked("");
    (void)register_voice_profile_name_locked(voice_name);

    tick_count++;
    commit_state_update_locked(VP_FLAG_VOL | VP_FLAG_VOICE_PROFILE_NUM |
                               VP_FLAG_AUDIO_OUT_NAME | VP_FLAG_WIFI_SSID | VP_FLAG_WIFI_PWD);

    unlock_state();
#endif
}
