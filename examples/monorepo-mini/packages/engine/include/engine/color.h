#pragma once

#include <cstdint>

namespace canvas {

struct Rgba {
  double r = 0.0;
  double g = 0.0;
  double b = 0.0;
  double a = 1.0;
};

// Decodes 0xRRGGBBAA into channels in the range [0.0, 1.0].
Rgba rgba_from_hex(std::uint32_t hex);

}  // namespace canvas
