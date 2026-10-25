#include "story/caveats.hpp"

#include <algorithm>
#include <functional>
#include <map>
#include <string>

#include "story/facts.hpp"

namespace story {

namespace {

using json = nlohmann::json;

const std::vector<std::string> kHospitals{"Hospital Geral", "Hospital Especializado", "Unidade Mista"};
const std::vector<std::string> kPrimaryCare{"Centro de Saúde/UBS", "Posto de Saúde"};

bool one_of(const std::vector<std::string>& list, const std::string& value) {
    return std::find(list.begin(), list.end(), value) != list.end();
}

double number_or(const json& row, const std::string& key, double fallback = 0) {
    return row.is_object() && row.contains(key) && row.at(key).is_number() ? row.at(key).get<double>() : fallback;
}

std::string text(const json& row, const std::string& key) {
    return row.is_object() && row.contains(key) && row.at(key).is_string() ? row.at(key).get<std::string>() : "";
}

double slot_number(const Fact& fact, const std::string& field) {
    auto it = fact.slots.find(field);
    return it == fact.slots.end() ? 0 : it->second.number;
}

bool planned(const Plan& plan, const std::string& id) {
    for (const auto& paragraph : plan.paragraphs) {
        if (std::find(paragraph.begin(), paragraph.end(), id) != paragraph.end()) return true;
    }
    return false;
}

Caveat caveat(const Rule& rule, const std::string& fact, std::string variant = {}) {
    return {rule.id, rule.effect, fact, std::move(variant), rule.before};
}

using PreRule = std::function<std::vector<Caveat>(const Payload&, const Rule&, std::vector<Fact>&)>;
using PostRule = std::function<std::vector<Caveat>(const Payload&, const Rule&, const std::vector<Fact>&, const Plan&)>;

// Note 1: a referral hospital serves the region, so per-resident figures around it mean nothing.
std::vector<Caveat> hub(const Payload& p, const Rule& rule, std::vector<Fact>& facts) {
    const double beds = rule.params.at("hub_beds").get<double>();
    if (one_of(kHospitals, text(p.facility, "tipo_equipamento")) && number_or(p.facility, "LEITOS_EXISTENTES") >= beds) {
        return {caveat(rule, "beds", "self")};
    }
    Fact* network = find_fact(facts, "network");
    if (network && slot_number(*network, "hubs_radius") > 0) {
        network->mandatory = true;
        return {caveat(rule, "network", "nearby")};
    }
    return {};
}

// Note 14: around a public primary care unit, the share of residents "far from primary care"
// comes from tracts that extend beyond the radius and contradicts the unit's own presence.
std::vector<Caveat> access_self(const Payload& p, const Rule& rule, std::vector<Fact>& facts) {
    const bool primary = one_of(kPrimaryCare, text(p.facility, "tipo_equipamento")) && p.facility.value("rede_sus", false);
    if (!primary || number_or(p.surroundings, "radius_m") > rule.params.at("max_radius_m").get<double>()) return {};
    auto it = std::find_if(facts.begin(), facts.end(), [](const Fact& f) { return f.id == "access"; });
    if (it == facts.end()) return {};
    facts.erase(it);
    return {caveat(rule, "access")};
}

// Note 15: a few cases move a rate a lot; give the count and drop the comparison.
std::vector<Caveat> small_counts(const Payload&, const Rule& rule, std::vector<Fact>& facts) {
    const double limit = rule.params.at("small_count").get<double>();
    const double penalty = rule.params.at("reliability").get<double>();
    std::vector<Caveat> out;
    for (auto& f : facts) {
        if (f.theme != "outcome") continue;
        for (const auto& [field, slot] : f.slots) {
            if (field.rfind("count_", 0) == 0 && slot.number < limit) {
                f.variant = "small";
                f.tier.reset();
                f.reliability *= penalty;
                out.push_back(caveat(rule, f.id));
                break;
            }
        }
    }
    return out;
}

std::vector<Caveat> when_planned(const Rule& rule, const Plan& plan, const std::string& fact, std::string variant = {}) {
    if (!planned(plan, fact)) return {};
    return {caveat(rule, fact, std::move(variant))};
}

// Note 3: low reliability when the circle covers large tracts only partly.
std::vector<Caveat> estimate_reliability(const Payload& p, const Rule& rule, const std::vector<Fact>&, const Plan& plan) {
    const double tracts = number_or(p.surroundings.value("census", json::object()).value("radius", json::object()), "tracts");
    if (radius_coverage(p) >= rule.params.at("low_coverage").get<double>() &&
        tracts >= rule.params.at("few_tracts").get<double>()) {
        return {};
    }
    return when_planned(rule, plan, "residents");
}

// Note 4: "not on the network" mixes septic tanks with precarious disposal.
std::vector<Caveat> septic(const Payload&, const Rule& rule, const std::vector<Fact>& facts, const Plan& plan) {
    const Fact* f = find_fact(facts, "sewage");
    if (!f || !planned(plan, "sewage") || !f->slots.count("precarious_radius")) return {};
    const double off = slot_number(*f, "radius");
    if (off < rule.params.at("min_share").get<double>()) return {};
    return {caveat(rule, "sewage", slot_number(*f, "precarious_radius") >= off / 2 ? "precarious" : "septic")};
}

// Note 6: much of the capacity nearby may be private and outside SUS.
std::vector<Caveat> private_share(const Payload&, const Rule& rule, const std::vector<Fact>& facts, const Plan& plan) {
    const Fact* f = find_fact(facts, "network");
    if (!f || !planned(plan, "network")) return {};
    const double total = slot_number(*f, "count_radius");
    if (total < rule.params.at("min_count").get<double>()) return {};
    if (slot_number(*f, "private_radius") / total < rule.params.at("min_share").get<double>()) return {};
    return {caveat(rule, "network")};
}

// Note 14: where most services nearby are private, being far from public primary care does not
// by itself mean unmet need; many residents use private insurance.
std::vector<Caveat> private_access(const Payload&, const Rule& rule, const std::vector<Fact>& facts, const Plan& plan) {
    const Fact* access = find_fact(facts, "access");
    const Fact* network = find_fact(facts, "network");
    if (!access || !network || !planned(plan, "access") || !access->tier) return {};
    const Tier t = *access->tier;
    if (t != Tier::Higher && t != Tier::MuchHigher && t != Tier::TimesHigher) return {};
    const double total = slot_number(*network, "count_radius");
    if (total == 0 || slot_number(*network, "private_radius") / total < rule.params.at("min_private_share").get<double>()) {
        return {};
    }
    return {caveat(rule, "access")};
}

// Note 8: a long stay reflects the case mix, not the quality of care.
std::vector<Caveat> long_stay(const Payload&, const Rule& rule, const std::vector<Fact>& facts, const Plan& plan) {
    const Fact* f = find_fact(facts, "stay");
    if (!f || f->variant != "long") return {};
    return when_planned(rule, plan, "stay");
}

// Notes 2, 10 and 11: outcome data do not exist for the radius; say so before the first one.
std::vector<Caveat> scale_bridge(const Payload&, const Rule& rule, const std::vector<Fact>& facts, const Plan& plan) {
    if (plan.paragraphs.size() < 3 || plan.paragraphs[2].empty()) return {};
    bool district = false, municipal = false;
    for (const auto& id : plan.paragraphs[2]) {
        const Fact* f = find_fact(facts, id);
        if (f && f->slots.count("district")) district = true;
        if (f && f->slots.count("municipality")) municipal = true;
    }
    std::string variant;
    if (district) variant = municipal ? "district_municipality" : "district";
    return {caveat(rule, plan.paragraphs[2].front(), variant)};
}

// Note 12: name an epidemic year when there was one.
std::vector<Caveat> epidemic(const Payload&, const Rule& rule, const std::vector<Fact>& facts, const Plan& plan) {
    const Fact* f = find_fact(facts, "dengue");
    if (!f || !planned(plan, "dengue")) return {};
    if (f->variant == "epidemic") return {caveat(rule, "dengue", "current")};
    if (f->slots.count("peak_year") && f->variant != "small") return {caveat(rule, "dengue")};
    return {};
}

// Note 17: district and municipal figures come from different systems.
std::vector<Caveat> sources(const Payload&, const Rule& rule, const std::vector<Fact>& facts, const Plan& plan) {
    if (plan.paragraphs.size() < 3) return {};
    std::string last_district;
    bool municipal = false;
    for (const auto& id : plan.paragraphs[2]) {
        const Fact* f = find_fact(facts, id);
        if (!f) continue;
        if (f->slots.count("district")) last_district = id;
        if (f->slots.count("municipality")) municipal = true;
    }
    if (last_district.empty() || !municipal) return {};
    return {caveat(rule, last_district)};
}

// Note 18: many deaths without a defined cause make the cause profile unreliable.
std::vector<Caveat> ill_defined(const Payload&, const Rule& rule, const std::vector<Fact>& facts, const Plan& plan) {
    const Fact* f = find_fact(facts, "mortality");
    if (!f || slot_number(*f, "ill_defined_municipality") <= rule.params.at("max_share").get<double>()) return {};
    return when_planned(rule, plan, "mortality");
}

PostRule always(const std::string& fact) {
    return [fact](const Payload&, const Rule& rule, const std::vector<Fact>&, const Plan& plan) {
        return when_planned(rule, plan, fact);
    };
}

const std::map<std::string, PreRule>& pre_rules() {
    static const std::map<std::string, PreRule> rules{
        {"C01", hub},
        {"C14", access_self},
        {"C15", small_counts},
    };
    return rules;
}

const std::map<std::string, PostRule>& post_rules() {
    static const std::map<std::string, PostRule> rules{
        {"C03", always("residents")},
        {"C03b", estimate_reliability},
        {"C04", septic},
        {"C05", always("position")},
        {"C06", private_share},
        {"C07", always("staff")},
        {"C08", always("admissions")},
        {"C08b", long_stay},
        {"C09", always("access")},
        {"C10", scale_bridge},
        {"C12", epidemic},
        {"C13", always("tb")},
        {"C14b", private_access},
        {"C16", always("tb_district")},
        {"C17", sources},
        {"C18", always("mortality")},
        {"C18b", ill_defined},
    };
    return rules;
}

}  // namespace

std::vector<Caveat> apply_pre_rules(const Payload& payload, const Config& config, std::vector<Fact>& facts) {
    std::vector<Caveat> out;
    for (const auto& rule : config.rules) {
        auto it = pre_rules().find(rule.id);
        if (it == pre_rules().end()) continue;
        auto found = it->second(payload, rule, facts);
        out.insert(out.end(), found.begin(), found.end());
    }
    return out;
}

std::vector<Caveat> apply_post_rules(const Payload& payload, const Config& config, const std::vector<Fact>& facts,
                                     const Plan& plan) {
    std::vector<Caveat> out;
    for (const auto& rule : config.rules) {
        auto it = post_rules().find(rule.id);
        if (it == post_rules().end()) continue;
        auto found = it->second(payload, rule, facts, plan);
        out.insert(out.end(), found.begin(), found.end());
    }
    return out;
}

}  // namespace story
