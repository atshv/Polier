#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

#include "color.h"

namespace canvas {

enum class NodeType : std::int32_t {
  kRect = 0,
  kEllipse = 1,
  kText = 2,
  kFrame = 3,
};

struct Node {
  std::uint64_t id = 0;
  NodeType type = NodeType::kRect;
  double x = 0.0;
  double y = 0.0;
  double width = 0.0;
  double height = 0.0;
  double rotation = 0.0;
  Rgba fill{};
};

struct Bounds {
  double min_x = 0.0;
  double min_y = 0.0;
  double max_x = 0.0;
  double max_y = 0.0;
};

// A document of nodes with one-way operations. No network, no storage, no DOM.
class Canvas {
 public:
  // Inserts a node and assigns a fresh id; a negative width or height is rejected.
  std::uint64_t insert_node(Node node);

  bool remove_node(std::uint64_t id);

  // Rejects a negative size instead of clamping it (P-3).
  bool set_size(std::uint64_t id, double width, double height);

  std::size_t node_count() const;

  const std::vector<Node>& nodes() const;

  // Bounding box of all nodes; all zero when the document is empty.
  Bounds document_bounds() const;

  // Writes the topmost node containing (x, y) to out_id; false when nothing is hit.
  bool hit_test(double x, double y, std::uint64_t* out_id) const;

 private:
  const Node* find(std::uint64_t id) const;

  std::vector<Node> nodes_;
  std::uint64_t next_id_ = 1;
};

// Contract version the C API was built against, e.g. 1 for 1.0.0.
std::int32_t contract_version_major();

}  // namespace canvas
