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
    bool public_only = false;

    nlohmann::json to_json() const;
    static Payload from_json(const nlohmann::json& j);
};

// Static reference data, loaded once.
struct Reference {
    std::vector<nlohmann::json> municipalities;
    std::vector<nlohmann::json> districts;
    std::vector<double> hospital_stays;
};

nlohmann::json sum_numeric(const std::vector<nlohmann::json>& rows);

// Strips tract geometry (only the per-tract shares are kept) and picks the matching
// municipality and district rows.
Payload assemble(nlohmann::json facility, nlohmann::json surroundings, const Reference& reference,
                 bool public_only);

}  // namespace story
