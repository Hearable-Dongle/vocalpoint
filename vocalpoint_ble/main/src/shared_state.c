/**************************************************************************************************/
/**
 * @file shared_state.c
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

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "configs.h"
#include "shared_state.h"

typedef struct {
    uint32_t seq;
    uint8_t volume;
    uint8_t battery;
    char ble_addr[VP_BLE_ADDR_MAX_LEN];
    char param1[VP_PARAM_MAX_LEN];
    char param2[VP_PARAM_MAX_LEN];
} vp_state_t;

static SemaphoreHandle_t s_state_mutex;
static vp_state_t s_state;
static uint8_t s_cached_frame[VP_I2C_FRAME_SIZE];

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
    memset(s_cached_frame, 0, sizeof(s_cached_frame));

    s_cached_frame[0] = VP_FRAME_MAGIC;
    s_cached_frame[1] = VP_FRAME_VERSION;

    s_cached_frame[2] = (uint8_t)(s_state.seq & 0xFFU);
    s_cached_frame[3] = (uint8_t)((s_state.seq >> 8) & 0xFFU);
    s_cached_frame[4] = (uint8_t)((s_state.seq >> 16) & 0xFFU);
    s_cached_frame[5] = (uint8_t)((s_state.seq >> 24) & 0xFFU);

    s_cached_frame[6] = s_state.volume;
    s_cached_frame[7] = s_state.battery;

    memcpy(&s_cached_frame[8], s_state.ble_addr, VP_BLE_ADDR_MAX_LEN);
    memcpy(&s_cached_frame[8 + VP_BLE_ADDR_MAX_LEN], s_state.param1, VP_PARAM_MAX_LEN);
    memcpy(&s_cached_frame[8 + VP_BLE_ADDR_MAX_LEN + VP_PARAM_MAX_LEN], s_state.param2, VP_PARAM_MAX_LEN);

    uint16_t crc = crc16_ccitt(s_cached_frame, VP_I2C_FRAME_SIZE - 2U);
    s_cached_frame[VP_I2C_FRAME_SIZE - 2U] = (uint8_t)(crc & 0xFFU);
    s_cached_frame[VP_I2C_FRAME_SIZE - 1U] = (uint8_t)((crc >> 8) & 0xFFU);
}

static void commit_state_update_locked(void)
{
    s_state.seq++;
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

static int set_battery_locked(uint8_t battery)
{
    uint8_t next = clamp_pct(battery);

    if (s_state.battery == next) {
        return 0;
    }

    s_state.battery = next;
    return 1;
}

static int set_ble_addr_locked(const char *addr)
{
    char next[VP_BLE_ADDR_MAX_LEN];

    copy_string(next, sizeof(next), addr);
    if (strings_equal(s_state.ble_addr, next)) {
        return 0;
    }

    copy_string(s_state.ble_addr, sizeof(s_state.ble_addr), next);
    return 1;
}

static int set_param1_locked(const char *value)
{
    char next[VP_PARAM_MAX_LEN];

    copy_string(next, sizeof(next), value);
    if (strings_equal(s_state.param1, next)) {
        return 0;
    }

    copy_string(s_state.param1, sizeof(s_state.param1), next);
    return 1;
}

static int set_param2_locked(const char *value)
{
    char next[VP_PARAM_MAX_LEN];

    copy_string(next, sizeof(next), value);
    if (strings_equal(s_state.param2, next)) {
        return 0;
    }

    copy_string(s_state.param2, sizeof(s_state.param2), next);
    return 1;
}

static int parse_and_apply_token_locked(char *token)
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
        return set_param1_locked(token);
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

        return set_volume_locked((uint8_t)parsed);
    }

    if (key_equals(key, "BAT") || key_equals(key, "BATTERY")) {
        long parsed = strtol(value, NULL, 10);

        if (parsed < 0L) {
            parsed = 0L;
        }
        if (parsed > 100L) {
            parsed = 100L;
        }

        return set_battery_locked((uint8_t)parsed);
    }

    if (key_equals(key, "ADDR") || key_equals(key, "BLE_ADDR")) {
        return set_ble_addr_locked(value);
    }

    if (key_equals(key, "P1") || key_equals(key, "PARAM1")) {
        return set_param1_locked(value);
    }

    if (key_equals(key, "P2") || key_equals(key, "PARAM2")) {
        return set_param2_locked(value);
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
#if I2C_TESTING_MODE
    s_state.volume = 2U;
    s_state.battery = 50U;
    copy_string(s_state.ble_addr, sizeof(s_state.ble_addr), "AA:BB:CC:DD:EE:FF");
    copy_string(s_state.param1, sizeof(s_state.param1), "Test Param 1");
    copy_string(s_state.param2, sizeof(s_state.param2), "Test Param 2");
#else
    s_state.volume = 50U;
    s_state.battery = 87U;
    copy_string(s_state.ble_addr, sizeof(s_state.ble_addr), "N/A");
    copy_string(s_state.param1, sizeof(s_state.param1), "");
    copy_string(s_state.param2, sizeof(s_state.param2), "");
#endif
    commit_state_update_locked();
    unlock_state();
}

void vp_state_set_volume(uint8_t volume)
{
    lock_state();
    if (set_volume_locked(volume)) {
        commit_state_update_locked();
    }
    unlock_state();
}

void vp_state_set_battery(uint8_t battery)
{
    lock_state();
    if (set_battery_locked(battery)) {
        commit_state_update_locked();
    }
    unlock_state();
}

void vp_state_set_ble_addr(const char *addr)
{
    lock_state();
    if (set_ble_addr_locked(addr)) {
        commit_state_update_locked();
    }
    unlock_state();
}

void vp_state_set_param1(const char *value)
{
    lock_state();
    if (set_param1_locked(value)) {
        commit_state_update_locked();
    }
    unlock_state();
}

void vp_state_set_param2(const char *value)
{
    lock_state();
    if (set_param2_locked(value)) {
        commit_state_update_locked();
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
    out->battery = s_state.battery;
    copy_string(out->ble_addr, sizeof(out->ble_addr), s_state.ble_addr);
    copy_string(out->param1, sizeof(out->param1), s_state.param1);
    copy_string(out->param2, sizeof(out->param2), s_state.param2);
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

    char buffer[128];
    size_t copy_len = payload_len;

    if (copy_len >= sizeof(buffer)) {
        copy_len = sizeof(buffer) - 1U;
    }

    memcpy(buffer, payload, copy_len);
    buffer[copy_len] = '\0';

    lock_state();

    int changed = 0;
    char *saveptr = NULL;
    char *token = strtok_r(buffer, ";,", &saveptr);
    while (token != NULL) {
        if (parse_and_apply_token_locked(token)) {
            changed = 1;
        }
        token = strtok_r(NULL, ";,", &saveptr);
    }

    if (changed) {
        commit_state_update_locked();
    }

    unlock_state();
}

void vp_state_testing_tick(void)
{
#if I2C_TESTING_MODE
    static uint8_t next_volume = 2U;
    static uint8_t next_battery = 50U;
    static uint32_t tick_count = 0U;
    char param1[VP_PARAM_MAX_LEN];

    lock_state();

    next_volume = (uint8_t)((next_volume + 3U) % 101U);
    next_battery = (uint8_t)(45U + (tick_count % 11U));

    set_volume_locked(next_volume);
    set_battery_locked(next_battery);
    set_ble_addr_locked("AA:BB:CC:DD:EE:FF");

    snprintf(param1, sizeof(param1), "Test Tick %lu", (unsigned long)tick_count);
    set_param1_locked(param1);
    set_param2_locked("Test Param 2");

    tick_count++;
    commit_state_update_locked();

    unlock_state();
#endif
}
