#include "story/facts.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <string>

namespace story {

namespace {

using json = nlohmann::json;

const std::vector<std::string> kHospitals{"Hospital Geral", "Hospital Especializado", "Unidade Mista"};
const std::vector<std::string> kPrimaryCare{"Centro de Saúde/UBS", "Posto de Saúde"};
const std::vector<std::string> kApproximate{"cnefe_street", "cnefe_cep"};
const std::vector<std::string> kDeathCauses{"ix", "ii", "x", "xx", "xi", "i"};
const char* const kIllDefined = "xviii";

bool one_of(const std::vector<std::string>& list, const std::string& value) {
    return std::find(list.begin(), list.end(), value) != list.end();
}

const json& child(const json& j, const std::string& key) {
    static const json missing;
    return j.is_object() && j.contains(key) ? j.at(key) : missing;
}

std::optional<double> number(const json& row, const std::string& key) {
    if (!row.is_object() || !row.contains(key)) return std::nullopt;
    const auto& v = row.at(key);
    if (v.is_number()) return v.get<double>();
    return std::nullopt;
}

double number_or(const json& row, const std::string& key, double fallback = 0) {
    return number(row, key).value_or(fallback);
}

std::string text(const json& row, const std::string& key) {
    if (!row.is_object() || !row.contains(key) || !row.at(key).is_string()) return {};
    return row.at(key).get<std::string>();
}

double param(const json& params, const std::string& key) { return params.at(key).get<double>(); }

double per100k(double cases, double population) { return population > 0 ? cases / population * 1e5 : 0; }

double percent(double part, double whole) { return whole > 0 ? part / whole * 100 : 0; }

std::vector<std::string> years(const json& params) { return params.at("sinan_years").get<std::vector<std::string>>(); }

double sum_years(const json& row, const std::string& prefix, const std::vector<std::string>& ys) {
    double total = 0;
    for (const auto& y : ys) total += number_or(row, prefix + "_" + y);
    return total;
}

double theme_weight(const json& params, const std::string& theme) {
    return params.at("theme_weights").value(theme, 1.0);
}

struct RadiusQuality {
    double reliability = 1;
};

RadiusQuality radius_quality(const Payload& p, const json& params) {
    const auto& r = params.at("reliability");
    RadiusQuality q;
    if (radius_coverage(p) < param(params, "low_coverage")) q.reliability *= r.at("low_coverage").get<double>();
    const auto tracts = number_or(child(child(p.surroundings, "census"), "radius"), "tracts");
    if (tracts < param(params, "few_tracts")) q.reliability *= r.at("few_tracts").get<double>();
    if (one_of(kApproximate, text(p.facility, "coord_source"))) {
        q.reliability *= r.at("approximate_position").get<double>();
    }
    return q;
}

// A census indicator for the radius against the municipality and the region.
std::optional<Fact> living_fact(const Payload& p, const json& params, const std::string& id, const std::string& theme,
                                const std::string& field, bool lacking, bool is_percent, int digits) {
    const auto& census = child(p.surroundings, "census");
    auto value = [&](const char* scope) -> std::optional<double> {
        auto v = number(child(census, scope), field);
        if (!v) return std::nullopt;
        return lacking ? std::round((100 - *v) * 10) / 10 : *v;
    };
    const auto radius = value("radius");
    const auto municipality = value("municipality");
    const auto region = value("region");
    if (!radius || !municipality || !region) return std::nullopt;

    Fact f;
    f.id = id;
    f.kind = "contrast";
    f.theme = theme;
    auto slot = [&](double v) { return is_percent ? Slot::percent(v) : Slot::decimal(v, digits); };
    f.slots["radius"] = slot(*radius);
    f.slots["municipality"] = slot(*municipality);
    f.slots["region"] = slot(*region);
    f.slots["municipality_name"] = Slot::text_value(text(child(p.surroundings, "location"), "municipality"));

    const auto local = compare(*radius, *municipality, is_percent, params);
    const auto wide = compare(*radius, *region, is_percent, params);
    f.tier = local.tier;
    if (local.tier == Tier::TimesHigher) f.slots["ratio"] = Slot::ratio(local.ratio);
    // The municipality is the primary reference; against the regional average almost any
    // central or peripheral area looks exceptional, so the region counts for less.
    f.salience = std::max(local.salience, param(params, "region_weight") * wide.salience);
    f.weight = theme_weight(params, theme);
    f.reliability = radius_quality(p, params).reliability;
    return f;
}

std::string network_class(const json& facility) {
    if (!facility.value("rede_sus", false)) return "private";
    return text(facility, "esfera_juridica") == "Administração Pública" ? "public" : "sus_partner";
}

void add_unit_facts(const Payload& p, const json& params, std::vector<Fact>& facts) {
    const auto& row = p.facility;
    const std::string type = text(row, "tipo_equipamento");
    std::string name = text(row, "NO_FANTASIA");
    if (name.find_first_not_of(' ') == std::string::npos) name = text(row, "NO_RAZAO_SOCIAL");

    Fact profile;
    profile.id = "profile";
    profile.kind = "profile";
    profile.theme = "unit";
    profile.mandatory = true;
    profile.salience = 1;
    profile.slots["name"] = Slot::text_value(name);
    profile.slots["type"] = Slot::label("type:" + type);
    profile.slots["network"] = Slot::label("network:" + network_class(row));
    const std::string flow = text(row, "Fluxo_Clientela");
    if (flow.empty()) {
        profile.variant = "noflow";
    } else {
        profile.slots["flow"] = Slot::label("flow:" + flow);
    }
    facts.push_back(profile);

    const double beds = number_or(row, "LEITOS_EXISTENTES");
    if (one_of(kHospitals, type) && beds > 0) {
        Fact f;
        f.id = "beds";
        f.kind = "value";
        f.theme = "unit";
        f.mandatory = true;
        f.salience = 1;
        f.slots["unit"] = Slot::count(beds);
        f.slots["sus_unit"] = Slot::count(number_or(row, "LEITOS_SUS"));
        f.slots["icu_unit"] = Slot::count(number_or(row, "UTI_TOTAL_EXIST"));
        f.slots["period"] = Slot::label("period:cnes");
        facts.push_back(f);
    } else {
        const double physicians = number_or(row, "total_medicos");
        const double nurses = number_or(row, "total_enfermeiros");
        if (physicians + nurses > 0) {
            Fact f;
            f.id = "staff";
            f.kind = "value";
            f.theme = "unit";
            f.mandatory = true;
            f.salience = 1;
            f.slots["physicians_unit"] = Slot::count(physicians);
            f.slots["nurses_unit"] = Slot::count(nurses);
            f.slots["period"] = Slot::label("period:cnes");
            facts.push_back(f);
        }
    }

    const double admissions = number_or(row, "internacoes_total");
    if (admissions > 0) {
        std::string top;
        double top_count = -1;
        for (const auto& [key, value] : row.items()) {
            if (key.rfind("internacoes_", 0) != 0 || key == "internacoes_total" || !value.is_number()) continue;
            if (value.get<double>() > top_count) {
                top = key;
                top_count = value.get<double>();
            }
        }
        Fact f;
        f.id = "admissions";
        f.kind = "composition";
        f.theme = "unit";
        f.salience = 0.8;
        f.slots["total_unit"] = Slot::count(admissions);
        f.slots["share_unit"] = Slot::percent(percent(top_count, admissions));
        f.slots["chapter"] = Slot::label("chapter:" + top);
        f.slots["period"] = Slot::label("period:sih");
        facts.push_back(f);

        const double stay = number_or(row, "media_dias_permanencia");
        if (stay > 0 && !p.hospital_stays.empty()) {
            const auto below = std::upper_bound(p.hospital_stays.begin(), p.hospital_stays.end(), stay);
            const double share = static_cast<double>(below - p.hospital_stays.begin()) / p.hospital_stays.size();
            const double cut = param(params, "rank_extreme");
            if (share >= 1 - cut || share <= cut) {
                Fact s;
                s.id = "stay";
                s.kind = "rank";
                s.theme = "unit";
                s.variant = share >= 1 - cut ? "long" : "short";
                s.salience = std::fabs(2 * share - 1);
                s.slots["days_unit"] = Slot::decimal(stay, 1);
                s.slots["period"] = Slot::label("period:sih");
                facts.push_back(s);
            }
        }
    }

    const std::string source = text(row, "coord_source");
    const bool corrected = source == "cnefe_corrected" &&
                           number_or(row, "coord_shift_m") >= param(params, "position_shift_min_m");
    if (one_of(kApproximate, source) || corrected) {
        Fact f;
        f.id = "position";
        f.kind = "quality";
        f.theme = "unit";
        f.mandatory = true;
        f.salience = 1;
        if (source == "cnefe_corrected") {
            f.variant = "corrected";
            f.slots["shift"] = Slot::distance(number_or(row, "coord_shift_m"));
        } else {
            f.variant = "approximate";
            f.slots["precision"] = Slot::distance(number_or(row, "coord_precision_m"));
        }
        facts.push_back(f);
    }
}

void add_radius_facts(const Payload& p, const json& params, std::vector<Fact>& facts) {
    const auto& census = child(p.surroundings, "census");
    const double radius_m = number_or(p.surroundings, "radius_m");

    Fact residents;
    residents.id = "residents";
    residents.kind = "value";
    residents.theme = "living";
    residents.mandatory = true;
    residents.salience = 1;
    residents.slots["radius"] = Slot::estimate(number_or(child(census, "radius"), "population"));
    residents.slots["households_radius"] = Slot::estimate(number_or(child(census, "radius"), "households"));
    residents.slots["extent_radius"] = Slot::distance(radius_m);
    residents.slots["period"] = Slot::label("period:census");
    residents.reliability = radius_quality(p, params).reliability;
    facts.push_back(residents);

    if (auto f = living_fact(p, params, "sewage", "living", "sewage_pct", true, true, 1)) {
        if (auto precarious = number(child(census, "radius"), "precarious_pct")) {
            f->slots["precarious_radius"] = Slot::percent(*precarious);
        }
        facts.push_back(*f);
    }
    if (auto f = living_fact(p, params, "precarious", "living", "precarious_pct", false, true, 1)) facts.push_back(*f);
    if (auto f = living_fact(p, params, "garbage", "living", "garbage_pct", true, true, 1)) facts.push_back(*f);
    if (auto f = living_fact(p, params, "crowding", "living", "residents_per_household", false, false, 2)) {
        facts.push_back(*f);
    }
    if (auto f = living_fact(p, params, "crowded", "living", "crowded_pct", false, true, 1)) {
        f->slots["threshold"] = Slot::decimal(number_or(p.surroundings, "crowding_threshold"), 1);
        facts.push_back(*f);
    }
    if (auto f = living_fact(p, params, "access", "access", "far_primary_pct", false, true, 1)) facts.push_back(*f);

    double total = 0, public_network = 0, hubs = 0;
    const double hub_beds = param(params, "hub_beds");
    for (const auto& n : p.surroundings.value("facilities", json::array())) {
        const bool sus = n.value("sus_network", false);
        if (p.public_only && !sus) continue;
        ++total;
        if (sus) ++public_network;
        if (one_of(kHospitals, text(n, "type")) && number_or(n, "beds") >= hub_beds) ++hubs;
    }
    Fact network;
    network.id = "network";
    network.kind = "composition";
    network.theme = "network";
    if (total == 0) {
        network.variant = "none";
    } else if (total == 1) {
        network.variant = public_network == 1 ? "one_public" : "one_private";
    }
    network.salience = total == 0 ? 0.8 : 0.4;
    network.weight = theme_weight(params, "network");
    network.slots["count_radius"] = Slot::count(total);
    network.slots["public_radius"] = Slot::count(public_network);
    network.slots["private_radius"] = Slot::count(total - public_network);
    network.slots["hubs_radius"] = Slot::count(hubs);
    network.slots["extent_radius"] = Slot::distance(radius_m);
    facts.push_back(network);
}

Fact outcome_fact(const std::string& id, const json& params, double local, double reference, bool is_percent,
                  int digits, const std::string& local_scope, const std::string& reference_scope) {
    Fact f;
    f.id = id;
    f.kind = "contrast";
    f.theme = "outcome";
    auto slot = [&](double v) { return is_percent ? Slot::percent(v) : Slot::rate(v, digits); };
    f.slots[local_scope] = slot(local);
    f.slots[reference_scope] = slot(reference);
    const auto c = compare(local, reference, is_percent, params);
    f.tier = c.tier;
    if (c.tier == Tier::TimesHigher) f.slots["ratio"] = Slot::ratio(c.ratio);
    f.salience = c.salience;
    f.weight = theme_weight(params, "outcome");
    return f;
}

void add_municipal_facts(const Payload& p, const json& params, std::vector<Fact>& facts) {
    const auto& home = p.municipality;
    const auto& region = p.region;
    if (!home.is_object() || home.empty()) return;
    const auto ys = years(params);
    const double pop = number_or(home, "populacao");
    const double region_pop = number_or(region, "populacao");
    const auto name = Slot::text_value(text(home, "nome"));
    const double n_years = static_cast<double>(ys.size());

    {
        const double cases = sum_years(home, "tuberculose", ys);
        auto f = outcome_fact("tb", params, per100k(cases / n_years, pop),
                              per100k(sum_years(region, "tuberculose", ys) / n_years, region_pop), false, 1,
                              "municipality", "region");
        f.slots["municipality_name"] = name;
        f.slots["count_municipality"] = Slot::count(cases);
        f.slots["period"] = Slot::label("period:sinan");
        f.pairs_with = {"crowding", "crowded"};
        facts.push_back(f);
    }
    {
        const std::string recent = params.at("recent_year");
        const double cases = number_or(home, "dengue_" + recent);
        auto f = outcome_fact("dengue", params, per100k(cases, pop),
                              per100k(number_or(region, "dengue_" + recent), region_pop), false, 0, "municipality",
                              "region");
        f.slots["municipality_name"] = name;
        f.slots["count_municipality"] = Slot::count(cases);
        f.slots["year"] = Slot::year(std::stoi(recent));
        f.pairs_with = {"sewage", "precarious", "garbage"};

        std::vector<std::pair<double, std::string>> by_year;
        for (const auto& y : ys) by_year.emplace_back(per100k(number_or(home, "dengue_" + y), pop), y);
        const auto peak = *std::max_element(by_year.begin(), by_year.end());
        std::vector<double> others;
        for (const auto& [rate, y] : by_year) {
            if (y != peak.second) others.push_back(rate);
        }
        std::sort(others.begin(), others.end());
        const double median = others.empty() ? 0 : others[others.size() / 2];
        if (median > 0 && peak.first >= param(params, "epidemic_factor") * median) {
            if (peak.second == recent) {
                f.variant = "epidemic";
            } else {
                f.slots["peak_year"] = Slot::year(std::stoi(peak.second));
                f.slots["peak_municipality"] = Slot::rate(peak.first, 0);
            }
        }
        facts.push_back(f);
    }
    {
        const double cases = sum_years(home, "lepto", ys);
        auto f = outcome_fact("lepto", params, per100k(cases / n_years, pop),
                              per100k(sum_years(region, "lepto", ys) / n_years, region_pop), false, 2, "municipality",
                              "region");
        f.slots["municipality_name"] = name;
        f.slots["count_municipality"] = Slot::count(cases);
        f.slots["period"] = Slot::label("period:sinan");
        f.pairs_with = {"sewage", "precarious"};
        facts.push_back(f);
    }
    {
        auto f = outcome_fact("teen", params,
                              percent(number_or(home, "nasc_mae_menor_20"), number_or(home, "nasc_idade_conhecida")),
                              percent(number_or(region, "nasc_mae_menor_20"), number_or(region, "nasc_idade_conhecida")),
                              true, 1, "municipality", "region");
        f.slots["municipality_name"] = name;
        f.slots["count_municipality"] = Slot::count(number_or(home, "nasc_mae_menor_20"));
        f.slots["period"] = Slot::label("period:births");
        facts.push_back(f);
    }
    {
        auto f = outcome_fact("preterm", params,
                              percent(number_or(home, "nasc_pretermo"), number_or(home, "nasc_gestacao_conhecida")),
                              percent(number_or(region, "nasc_pretermo"), number_or(region, "nasc_gestacao_conhecida")),
                              true, 1, "municipality", "region");
        f.slots["municipality_name"] = name;
        f.slots["count_municipality"] = Slot::count(number_or(home, "nasc_pretermo"));
        f.slots["period"] = Slot::label("period:births");
        facts.push_back(f);
    }
    {
        // Cause shares among deaths with a defined cause, as on the mortality card.
        auto defined = [](const json& row) {
            return number_or(row, "obitos_total") - number_or(row, std::string("obitos_cap_") + kIllDefined);
        };
        std::string top;
        double top_share = -1;
        for (const auto& c : kDeathCauses) {
            const double share = percent(number_or(home, "obitos_cap_" + c), defined(home));
            if (share > top_share) {
                top = c;
                top_share = share;
            }
        }
        auto f = outcome_fact("mortality", params, top_share,
                              percent(number_or(region, "obitos_cap_" + top), defined(region)), true, 1,
                              "municipality", "region");
        f.slots["municipality_name"] = name;
        f.slots["cause"] = Slot::label("cause:" + top);
        f.slots["count_municipality"] = Slot::count(defined(home));
        f.slots["ill_defined_municipality"] = Slot::percent(
            percent(number_or(home, std::string("obitos_cap_") + kIllDefined), number_or(home, "obitos_total")));
        f.slots["period"] = Slot::label("period:deaths");
        facts.push_back(f);
    }
}

void add_district_facts(const Payload& p, const json& params, std::vector<Fact>& facts) {
    if (!p.district.is_object() || p.district.empty()) return;
    const auto ys = years(params);
    const double n_years = static_cast<double>(ys.size());
    auto tb_rate = [&](const json& row) {
        return per100k(sum_years(row, "tb", ys) / n_years, number_or(row, "populacao_total"));
    };
    const auto name = Slot::text_value(text(p.district, "nm_dist"));
    const double boost = param(params, "district_boost");

    {
        const double rate = tb_rate(p.district);
        auto f = outcome_fact("tb_district", params, rate, tb_rate(p.city), false, 1, "district", "city");
        f.slots["district_name"] = name;
        f.slots["count_district"] = Slot::count(sum_years(p.district, "tb", ys));
        f.slots["period"] = Slot::label("period:sinan");
        f.pairs_with = {"crowding", "crowded"};
        f.weight *= boost;

        std::size_t above = 0, total = 0;
        for (const auto& row : p.districts) {
            ++total;
            if (tb_rate(row) > rate) ++above;
        }
        const std::size_t top = static_cast<std::size_t>(param(params, "district_top"));
        if (above < top) f.variant = "top";
        if (total >= top && above >= total - top) f.variant = "bottom";
        facts.push_back(f);
    }
    {
        auto share = [](const json& row) {
            return percent(number_or(row, "nasc_mae_menor_20"), number_or(row, "nasc_idade_conhecida"));
        };
        auto f = outcome_fact("teen_district", params, share(p.district), share(p.city), true, 1, "district", "city");
        f.slots["district_name"] = name;
        f.slots["count_district"] = Slot::count(number_or(p.district, "nasc_mae_menor_20"));
        f.slots["period"] = Slot::label("period:births");
        f.weight *= boost;
        facts.push_back(f);
    }
}

}  // namespace

Comparison compare(double local, double reference, bool is_percent, const json& params) {
    const double saturation_ratio = param(params, "saturation_ratio");
    const double saturation_pp = param(params, "saturation_pp");
    Comparison c;
    if (reference > 0) c.ratio = local / reference;

    double smoothed = 1;
    if (reference > 0 && local > 0) {
        smoothed = local / reference;
    } else if (local != reference) {
        smoothed = saturation_ratio;
    }
    // Shares compare by absolute difference: a relative difference between small shares
    // exaggerates (Trevena et al. 2013). Rates and averages compare by ratio.
    const double s = is_percent ? std::fabs(local - reference) / saturation_pp
                                : std::fabs(std::log(smoothed)) / std::log(saturation_ratio);
    c.salience = std::min(1.0, s);

    double r = 1;
    if (reference > 0) {
        r = local / reference;
    } else if (local > 0) {
        r = std::numeric_limits<double>::infinity();
    }
    const bool similar = (r > 0 && std::fabs(std::log(r)) < std::log(param(params, "similar_ratio"))) ||
                         (is_percent && std::fabs(local - reference) < param(params, "similar_pp")) ||
                         local == reference;
    const double higher = param(params, "higher_ratio");
    const double times = param(params, "times_ratio");
    if (similar) {
        c.tier = Tier::Similar;
    } else if (r > 1) {
        if (r < higher) {
            c.tier = Tier::Higher;
        } else if (r < times || reference <= 0) {
            c.tier = Tier::MuchHigher;
        } else {
            c.tier = Tier::TimesHigher;
        }
    } else {
        c.tier = r > 1 / higher ? Tier::Lower : Tier::MuchLower;
    }
    return c;
}

double radius_coverage(const Payload& payload) {
    double inside = 0, total = 0;
    for (const auto& t : payload.surroundings.value("tracts", json::array())) {
        const double pop = t.value("population", 0.0);
        inside += pop * t.value("share_inside", 0.0);
        total += pop;
    }
    return total > 0 ? inside / total : 1;
}

std::vector<Fact> extract_facts(const Payload& payload, const json& params) {
    std::vector<Fact> facts;
    add_unit_facts(payload, params, facts);
    add_radius_facts(payload, params, facts);
    add_district_facts(payload, params, facts);
    add_municipal_facts(payload, params, facts);
    return facts;
}

}  // namespace story
