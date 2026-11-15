#include "story/payload.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <optional>

namespace story {

namespace {

using json = nlohmann::json;

const char* const kSaoPaulo = "355030";
const int kReferenceRadius = 1000;

// The five colour groups of the map (public/js/fields.js).
const std::map<std::string, std::string> kGroups{
    {"Centro de Saúde/UBS", "primary"},
    {"Posto de Saúde", "primary"},
    {"Polo Academia da Saúde", "primary"},
    {"Hospital Geral", "hospital"},
    {"Hospital Especializado", "hospital"},
    {"Unidade Mista", "hospital"},
    {"Pronto Atendimento (UPA)", "emergency"},
    {"Pronto Socorro Geral", "emergency"},
    {"Pronto Socorro Especializado", "emergency"},
    {"Policlínica", "specialised"},
    {"Clínica/Centro de Especialidade", "specialised"},
    {"Centro de Atenção Psicossocial (CAPS)", "specialised"},
    {"Unidade de Apoio Diagnose e Terapia (SADT Isolado)", "diagnostic"},
};

std::optional<double> number(const json& row, const char* key) {
    if (!row.contains(key) || !row.at(key).is_number()) return std::nullopt;
    return row.at(key).get<double>();
}

std::string group_of(const json& row) {
    auto it = kGroups.find(field_or<std::string>(row, "tipo_equipamento", ""));
    return it == kGroups.end() ? "" : it->second;
}

bool public_primary(const json& row) {
    const std::string type = field_or<std::string>(row, "tipo_equipamento", "");
    return field_or(row, "rede_sus", false) && (type == "Centro de Saúde/UBS" || type == "Posto de Saúde");
}

// Indicators compared across peers; shares of households or residents, and income.
std::map<std::string, std::optional<double>> indicators(const json& row) {
    std::map<std::string, std::optional<double>> out;
    out["precarious"] = number(row, "precarious_pct");
    if (auto v = number(row, "sewage_pct")) out["off_network"] = 100 - *v;
    if (auto v = number(row, "garbage_pct")) out["no_garbage"] = 100 - *v;
    out["crowded"] = number(row, "crowded_pct");
    out["far_primary"] = number(row, "far_primary_pct");
    out["income"] = number(row, "income");
    const auto population = number(row, "population");
    if (population && *population > 0) {
        out["deprived"] = 100 * number(row, "deprived_population").value_or(0) / *population;
        const double units = number(row, "public_primary_nearby").value_or(0) + (public_primary(row) ? 1 : 0);
        if (units > 0) out["load"] = *population / units;
    }
    return out;
}

double percentile(std::vector<double> values, double v) {
    if (values.empty()) return 0.5;
    const double below = std::count_if(values.begin(), values.end(), [&](double x) { return x < v; });
    const double equal = std::count_if(values.begin(), values.end(), [&](double x) { return x == v; });
    return (below + equal / 2) / values.size();
}

}  // namespace

json reference_context(const json& facility, const Reference& reference) {
    const long long cnes = field_or(facility, "CO_CNES", 0LL);
    const json* own = nullptr;
    for (const auto& row : reference.surroundings) {
        if (field_or(row, "cnes", 0LL) == cnes) own = &row;
    }
    if (!own) return nullptr;
    const std::string group = group_of(*own);
    const auto mine = indicators(*own);

    std::map<std::string, std::vector<double>> peers, public_primary_peers;
    std::size_t group_size = 0, type_size = 0, public_primary_size = 0;
    const auto type = field_or(*own, "territory_type", 0);
    for (const auto& row : reference.surroundings) {
        if (field_or(row, "territory_type", 0) == type && type) ++type_size;
        if (group_of(row) != group) continue;
        ++group_size;
        const bool primary = public_primary(row);
        if (primary) ++public_primary_size;
        for (const auto& [name, value] : indicators(row)) {
            if (!value) continue;
            peers[name].push_back(*value);
            if (primary) public_primary_peers[name].push_back(*value);
        }
    }

    json values = json::object(), percentiles = json::object();
    for (const auto& [name, value] : mine) {
        if (!value || name == "load") continue;
        values[name] = *value;
        percentiles[name] = percentile(peers[name], *value);
    }
    json context{{"radius", kReferenceRadius},
                 {"group", group},
                 {"group_size", group_size},
                 {"facilities", reference.surroundings.size()},
                 {"territory_type", type},
                 {"type_size", type_size},
                 {"values", values},
                 {"percentiles", percentiles}};
    if (!public_primary(*own)) return context;

    // Need and supply over the residents the unit is expected to serve, when the catchment model
    // covers it; otherwise over the reference radius, which rule C21 qualifies in sparse areas.
    const auto served = number(*own, "served_population");
    const auto served_deprived = number(*own, "served_deprived_pct");
    if (served && served_deprived && *served > 0) {
        std::vector<double> loads, needs;
        for (const auto& row : reference.surroundings) {
            if (!public_primary(row)) continue;
            const auto s = number(row, "served_population");
            const auto d = number(row, "served_deprived_pct");
            if (s && d && *s > 0) {
                loads.push_back(*s);
                needs.push_back(*d);
            }
        }
        context["supply_measure"] = "catchment";
        context["public_primary_size"] = loads.size();
        context["need_percentile"] = percentile(needs, *served_deprived);
        context["load_percentile"] = percentile(loads, *served);
        context["values"]["served"] = *served;
        context["values"]["served_deprived"] = *served_deprived;
        context["near_edge"] = field_or(*own, "near_edge", false);
        if (const auto m = number(*own, "mean_catchment_m")) context["mean_catchment_m"] = *m;
        if (const auto e = number(*own, "edge_m")) context["edge_m"] = *e;
        if (const auto t = number(*own, "team_equivalents")) context["team_equivalents"] = *t;
        if (const auto t = number(*own, "served_per_team")) context["values"]["served_per_team"] = *t;
        if (const auto d = number(*own, "served_mean_distance_m")) context["values"]["served_mean_distance"] = *d;
        if (const auto d = number(*own, "served_far_pct")) context["values"]["served_far"] = *d;
    } else if (mine.count("deprived") && mine.at("deprived")) {
        context["supply_measure"] = "radius";
        context["public_primary_size"] = public_primary_size;
        context["need_percentile"] = percentile(public_primary_peers["deprived"], *mine.at("deprived"));
        if (mine.count("load") && mine.at("load")) {
            context["values"]["load"] = *mine.at("load");
            context["load_percentile"] = percentile(public_primary_peers["load"], *mine.at("load"));
        }
    }
    if (const auto population = number(*own, "population")) context["values"]["population"] = *population;
    return context;
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
            {"districts", districts},           {"context", context},           {"expected", expected},
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
    p.context = j.value("context", nlohmann::json());
    p.expected = j.value("expected", nlohmann::json::array());
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

    p.context = reference_context(p.facility, reference);
    const std::string district = p.district.is_object() ? p.district.value("cd_dist", "") : "";
    p.expected = nlohmann::json::array();
    for (const auto& row : reference.expected) {
        const std::string scale = field_or<std::string>(row, "scale", "");
        const std::string code = field_or<std::string>(row, "code", "");
        if ((scale == "district" && code == district) || (scale == "municipality" && code == municipality)) {
            p.expected.push_back(row);
        }
    }
    return p;
}

}  // namespace story
