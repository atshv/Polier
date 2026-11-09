#include "../include/engine/canvas.h"

#include <algorithm>
#include <limits>

namespace canvas {

std::int32_t contract_version_major() { return 1; }

const Node* Canvas::find(std::uint64_t id) const {
  const auto it = std::find_if(nodes_.begin(), nodes_.end(),
                               [id](const Node& node) { return node.id == id; });
  return it == nodes_.end() ? nullptr : &*it;
}

std::uint64_t Canvas::insert_node(Node node) {
  if (node.width < 0.0 || node.height < 0.0) {
    return 0;
  }
  node.id = next_id_++;
  nodes_.push_back(node);
  return node.id;
}

bool Canvas::remove_node(std::uint64_t id) {
  const auto it = std::find_if(nodes_.begin(), nodes_.end(),
                               [id](const Node& node) { return node.id == id; });
  if (it == nodes_.end()) {
    return false;
  }
  nodes_.erase(it);
  return true;
}

bool Canvas::set_size(std::uint64_t id, double width, double height) {
  if (width < 0.0 || height < 0.0) {
    return false;
  }
  const auto it = std::find_if(nodes_.begin(), nodes_.end(),
                               [id](const Node& node) { return node.id == id; });
  if (it == nodes_.end()) {
    return false;
  }
  it->width = width;
  it->height = height;
  return true;
}

std::size_t Canvas::node_count() const { return nodes_.size(); }

const std::vector<Node>& Canvas::nodes() const { return nodes_; }

Bounds Canvas::document_bounds() const {
  if (nodes_.empty()) {
    return Bounds{};
  }
  Bounds bounds;
  bounds.min_x = std::numeric_limits<double>::max();
  bounds.min_y = std::numeric_limits<double>::max();
  bounds.max_x = std::numeric_limits<double>::lowest();
  bounds.max_y = std::numeric_limits<double>::lowest();
  for (const Node& node : nodes_) {
    bounds.min_x = std::min(bounds.min_x, node.x);
    bounds.min_y = std::min(bounds.min_y, node.y);
    bounds.max_x = std::max(bounds.max_x, node.x + node.width);
    bounds.max_y = std::max(bounds.max_y, node.y + node.height);
  }
  return bounds;
}

bool Canvas::hit_test(double x, double y, std::uint64_t* out_id) const {
  for (auto it = nodes_.rbegin(); it != nodes_.rend(); ++it) {
    if (x >= it->x && x <= it->x + it->width && y >= it->y && y <= it->y + it->height) {
      if (out_id != nullptr) {
        *out_id = it->id;
      }
      return true;
    }
  }
  return false;
}

}  // namespace canvas
