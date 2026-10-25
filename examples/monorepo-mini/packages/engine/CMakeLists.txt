cmake_minimum_required(VERSION 3.28)
project(canvas_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(canvas_engine STATIC
  src/canvas.cpp
  src/color.cpp
)
target_include_directories(canvas_engine PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_options(canvas_engine PRIVATE -Wall -Wextra -Wpedantic)

# The test target and the CTest registration are added by ENG-01.

if(EMSCRIPTEN)
  add_executable(canvas_engine_wasm src/wasm_bindings.cpp)
  target_link_libraries(canvas_engine_wasm PRIVATE canvas_engine)
  set_target_properties(canvas_engine_wasm PROPERTIES
    OUTPUT_NAME canvas_engine_wasm
    SUFFIX ".js"
  )
endif()
