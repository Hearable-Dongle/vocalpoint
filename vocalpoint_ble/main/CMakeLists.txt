set(srcs
    "src/main.c"
    "src/ble_manager.c"
    "src/ble_gatt_server.c"
    "src/i2c_bridge.c")

idf_component_register(SRCS "${srcs}"
                       INCLUDE_DIRS "include")
