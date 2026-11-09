#include "../include/engine/color.h"

namespace canvas {

Rgba rgba_from_hex(std::uint32_t hex) {
  Rgba color;
  color.r = static_cast<double>((hex >> 24U) & 0xFFU) / 255.0;
  color.g = static_cast<double>((hex >> 16U) & 0xFFU) / 255.0;
  color.b = static_cast<double>((hex >> 8U) & 0xFFU) / 255.0;
  color.a = static_cast<double>(hex & 0xFFU) / 255.0;
  return color;
}

}  // namespace canvas
