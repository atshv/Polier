// C API of the engine for the WebAssembly build (ENG-02 owns this file).
// Only primitive types cross this border (P-2); the C++ classes stay internal.
#include "../include/engine/canvas.h"

extern "C" {

std::int32_t canvas_contract_version_major() {
  return canvas::contract_version_major();
}

std::int32_t canvas_node_count(const canvas::Canvas* document) {
  if (document == nullptr) {
    return 0;
  }
  return static_cast<std::int32_t>(document->node_count());
}

}  // extern "C"
