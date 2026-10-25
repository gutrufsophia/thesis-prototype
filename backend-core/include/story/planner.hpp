#pragma once

#include <vector>

#include <nlohmann/json.hpp>

#include "story/model.hpp"

namespace story {

// Document schema (McKeown-style): ¶1 the unit, ¶2 its surroundings within the radius,
// ¶3 health outcomes at the scales where they exist. Greedy selection by importance under
// the schema's limits. Outcome facts related to a selected living-condition fact get a boost,
// which is written into their weight so the reported importance is the one used.
Plan plan_document(std::vector<Fact>& facts, const nlohmann::json& params);

}  // namespace story
