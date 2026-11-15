#pragma once

#include <cstddef>
#include <vector>

#include <nlohmann/json.hpp>

#include "story/model.hpp"
#include "story/payload.hpp"

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
Plan plan_document(std::vector<Fact>& facts, const nlohmann::json& params,
                   const std::vector<std::string>& lead_candidates);

// Facts that may open the text, by the facility's role. A referral hospital serves the whole region,
// so nothing about its surroundings or district leads (note 1); district outcomes describe the
// population of a primary care unit, not that of a specialised service.
std::vector<std::string> lead_candidates(const Payload& payload, const nlohmann::json& params);

}  // namespace story
