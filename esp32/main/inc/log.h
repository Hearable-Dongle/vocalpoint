/**************************************************************************************************/
/**
 * @file log.h
 * @author
 * @brief Shared logging helpers for source files.
 *
 * @version 0.1
 * @date 2026-03-26
 *
 * @copyright Copyright (c) 2026
 *
 */
/**************************************************************************************************/

#ifndef LOG_H_
#define LOG_H_

#ifdef __cplusplus
extern "C" {
#endif

/**************************************************************************************************/
/**
 * @name LOG_TAG
 * @brief Per-file tag string override.
 *
 * Define `LOG_TAG` before including this header in a `.c` file to customize
 * that file's log tag. If not defined, the default tag `"esp32_app"` is used.
 */
/**************************************************************************************************/
#define LOG_TAG "esp32_app"

/**************************************************************************************************/
/**
 * @name s_tag
 * @brief Standardized tag variable used by ESP_LOGx calls.
 */
/**************************************************************************************************/
static const char *s_tag = LOG_TAG;

#ifdef __cplusplus
}
#endif

#endif
