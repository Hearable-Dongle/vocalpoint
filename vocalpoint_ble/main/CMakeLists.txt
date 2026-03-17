set(srcs
    "src/main.c"
    "src/ble_manager.c"
    "src/ble_gatt_server.c"
    "src/i2c_bridge.c"
    "src/shared_state.c")

idf_component_register(SRCS "${srcs}"
                       INCLUDE_DIRS "include"
                       REQUIRES bt
                                esp_driver_gpio
                                esp_driver_i2c
                                nimble_peripheral_utils
                                nvs_flash)
