#pragma once

#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace story {

// Everything the narrative is built from. Taken from the same PostgREST functions the
// facility page uses, so the text and the cards show the same figures.
struct Payload {
    nlohmann::json facility;      // row of infraestrutura_saude
    nlohmann::json surroundings;  // facility_surroundings(), tract geometry removed
    nlohmann::json municipality;  // row of municipal_indicators() for the facility's municipality
    nlohmann::json region;        // sum of all municipal rows
    nlohmann::json district;      // row of district_indicators(), or null outside São Paulo city
    nlohmann::json city;          // sum of all district rows, or null
    nlohmann::json districts;     // every district row, for ranks; null outside São Paulo city
    std::vector<double> hospital_stays;  // mean length of stay of every hospital with admissions, sorted
    // Position among peer facilities at the reference radius (see reference_context), or null.
    nlohmann::json context;
    // Observed against model-expected counts for the facility's district and municipality.
    nlohmann::json expected;
    bool public_only = false;

    nlohmann::json to_json() const;
    static Payload from_json(const nlohmann::json& j);
};

// Static reference data, loaded once.
struct Reference {
    std::vector<nlohmann::json> municipalities;
    std::vector<nlohmann::json> districts;
    std::vector<double> hospital_stays;
    std::vector<nlohmann::json> surroundings;  // 1 km surroundings of every mapped facility
    std::vector<nlohmann::json> expected;      // observed against expected counts by area
};

// The facility's 1 km surroundings ranked against facilities of the same type group: a
// percentile (share of peers with a lower value, ties counted half) for each indicator, the
// share of residents in deprived tracts, residents per public primary care unit, and the
// territorial type. Null when the facility is not in the reference.
nlohmann::json reference_context(const nlohmann::json& facility, const Reference& reference);

nlohmann::json sum_numeric(const std::vector<nlohmann::json>& rows);

// row[key] when present and not null; nlohmann's value() throws on a null it finds.
template <typename T>
T field_or(const nlohmann::json& row, const char* key, T fallback) {
    if (!row.is_object() || !row.contains(key) || row.at(key).is_null()) return fallback;
    return row.at(key).get<T>();
}

// Strips tract geometry (only the per-tract shares are kept) and picks the matching
// municipality and district rows.
Payload assemble(nlohmann::json facility, nlohmann::json surroundings, const Reference& reference,
                 bool public_only);

}  // namespace story
