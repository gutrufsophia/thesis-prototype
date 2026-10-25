#include "story/payload.hpp"

#include <algorithm>

namespace story {

namespace {
const char* const kSaoPaulo = "355030";
}

nlohmann::json sum_numeric(const std::vector<nlohmann::json>& rows) {
    nlohmann::json total = nlohmann::json::object();
    for (const auto& row : rows) {
        for (const auto& [key, value] : row.items()) {
            if (!value.is_number()) continue;
            total[key] = total.value(key, 0.0) + value.get<double>();
        }
    }
    return total;
}

nlohmann::json Payload::to_json() const {
    return {{"facility", facility},         {"surroundings", surroundings}, {"municipality", municipality},
            {"region", region},             {"district", district},         {"city", city},
            {"districts", districts},
            {"hospital_stays", hospital_stays}, {"public_only", public_only}};
}

Payload Payload::from_json(const nlohmann::json& j) {
    Payload p;
    p.facility = j.at("facility");
    p.surroundings = j.at("surroundings");
    p.municipality = j.at("municipality");
    p.region = j.at("region");
    p.district = j.value("district", nlohmann::json());
    p.city = j.value("city", nlohmann::json());
    p.districts = j.value("districts", nlohmann::json());
    p.hospital_stays = j.value("hospital_stays", std::vector<double>{});
    p.public_only = j.value("public_only", false);
    return p;
}

Payload assemble(nlohmann::json facility, nlohmann::json surroundings, const Reference& reference,
                 bool public_only) {
    Payload p;
    p.facility = std::move(facility);
    p.public_only = public_only;
    p.hospital_stays = reference.hospital_stays;

    if (surroundings.contains("tracts")) {
        nlohmann::json shares = nlohmann::json::array();
        for (const auto& feature : surroundings["tracts"].value("features", nlohmann::json::array())) {
            const auto& props = feature.at("properties");
            shares.push_back({{"share_inside", props.value("share_inside", 0.0)},
                              {"population", props.value("population", 0.0)}});
        }
        surroundings["tracts"] = shares;
    }
    p.surroundings = std::move(surroundings);

    const auto location = p.surroundings.value("location", nlohmann::json::object());
    const std::string municipality = location.value("municipality_code", "");
    for (const auto& row : reference.municipalities) {
        if (row.value("cd_municipio6", "") == municipality) p.municipality = row;
    }
    p.region = sum_numeric(reference.municipalities);

    // A tract code starts with its district code: UF, municipality and district (9 digits).
    const std::string tract = location.value("tract", "");
    if (municipality == kSaoPaulo && tract.size() >= 9) {
        const std::string code = tract.substr(0, 9);
        for (const auto& row : reference.districts) {
            if (row.value("cd_dist", "") == code) p.district = row;
        }
        if (!p.district.is_null()) {
            p.city = sum_numeric(reference.districts);
            p.districts = reference.districts;
        }
    }
    return p;
}

}  // namespace story
