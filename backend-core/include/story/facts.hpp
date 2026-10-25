#pragma once

#include <vector>

#include <nlohmann/json.hpp>

#include "story/model.hpp"
#include "story/payload.hpp"

namespace story {

struct Comparison {
    double salience = 0;
    Tier tier = Tier::Similar;
    double ratio = 0;  // local / reference, 0 when undefined
};

// Salience and lexical tier of a local value against its reference.
// Percentages: s = min(1, |Δpp| / saturation_pp). Rates and averages: s = min(1, |ln r| / ln saturation_ratio).
Comparison compare(double local, double reference, bool is_percent, const nlohmann::json& params);

// Share of the radius tracts' population that lies inside the circle. Low values mean the
// areal-weighting estimates lean on large tracts that extend far beyond the radius.
double radius_coverage(const Payload& payload);

std::vector<Fact> extract_facts(const Payload& payload, const nlohmann::json& params);

}  // namespace story
