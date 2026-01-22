# firmware-esp32/CMakeLists.txt

cmake_minimum_required(VERSION 3.16)

# If you have extra components in a local folder, uncomment and point to it:
# set(EXTRA_COMPONENT_DIRS ${CMAKE_SOURCE_DIR}/components)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Name of the project (affects ELF/firmware file names)
project(vocalpoint_fw)
