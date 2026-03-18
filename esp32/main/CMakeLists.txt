set(srcs
    "src/main.c"
    "src/ble_manager.c"
    "src/ble_gatt_server.c"
    "src/i2c.c"
    "src/state.c")

idf_build_get_property(idf_path IDF_PATH)

idf_component_register(SRCS "${srcs}"
                       INCLUDE_DIRS "include"
                       PRIV_INCLUDE_DIRS "${idf_path}/components/esp_driver_i2c"
                       REQUIRES bt
                                esp_driver_gpio
                                esp_driver_i2c
                                esp_pm
                                esp_ringbuf
                                nimble_peripheral_utils
                                nvs_flash)
