set(SRC_FILES app_main.c)
idf_component_register(SRCS ${SRC_FILES} INCLUDE_DIRS . REQUIRES bt nvs_flash)
