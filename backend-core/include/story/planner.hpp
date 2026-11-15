#pragma once

#include <cstddef>
#include <vector>

#include <nlohmann/json.hpp>

#include "story/model.hpp"

namespace story {

// Paragraph slots of every plan; a slot may be empty.
inline constexpr std::size_t kLead = 0;
inline constexpr std::size_t kUnit = 1;
inline constexpr std::size_t kSurroundings = 2;
inline constexpr std::size_t kOutcomes = 3;

// Document schema (McKeown-style) in the order of the inverted pyramid: a lead sentence with the
// most newsworthy comparison, then the unit, its surroundings, and health outcomes at the scales
// where they exist. Greedy selection by importance under the schema's limits. Outcome facts
// related to a selected living-condition fact get a boost, written into their weight so the
// reported importance is the one used.
Plan plan_document(std::vector<Fact>& facts, const nlohmann::json& params);

}  // namespace story
