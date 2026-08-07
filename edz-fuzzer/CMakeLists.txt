cmake_minimum_required(VERSION 3.16)
project(fuzz_edz LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt5 REQUIRED COMPONENTS Core Xml)

# Path to the EDZ sources — override with -DEDZ_SRC=...
if(NOT EDZ_SRC)
    set(EDZ_SRC "${CMAKE_SOURCE_DIR}/../edz_src")
endif()

set(LZMA_DIR "${EDZ_SRC}/lzma")

file(GLOB LZMA_C_SRCS "${LZMA_DIR}/*.c")

add_executable(fuzz_edz
    fuzz_edz.cpp
    ${EDZ_SRC}/edzarchive.cpp
    ${EDZ_SRC}/edzpart.cpp
    ${EDZ_SRC}/edzelementbuilder.cpp
    ${EDZ_SRC}/edzimporter.cpp
    ${EDZ_SRC}/edzsevenzip.cpp
    ${LZMA_C_SRCS}
)

target_include_directories(fuzz_edz PRIVATE ${EDZ_SRC} ${LZMA_DIR})
target_link_libraries(fuzz_edz PRIVATE Qt5::Core Qt5::Xml)

if(ASAN)
    target_compile_options(fuzz_edz PRIVATE
        -fsanitize=address,undefined
        -fno-omit-frame-pointer
        -g
    )
    target_link_options(fuzz_edz PRIVATE -fsanitize=address,undefined)
endif()
