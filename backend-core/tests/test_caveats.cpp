#include <algorithm>
#include <array>
#include <utility>
#include <vector>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include "helpers.hpp"
#include "story/caveats.hpp"
#include "story/facts.hpp"
#include "story/narrative.hpp"
#include "story/planner.hpp"

namespace {

using Catch::Approx;
using story::Caveat;
using story::Effect;

bool has(const std::vector<Caveat>& caveats, const std::string& rule, const std::string& variant = "*") {
    return std::any_of(caveats.begin(), caveats.end(),
                       [&](const Caveat& c) { return c.rule == rule && (variant == "*" || c.variant == variant); });
}

std::vector<Caveat> all_caveats(const story::Story& s) {
    auto out = s.plan.caveats;
    out.insert(out.end(), s.suppressed.begin(), s.suppressed.end());
    return out;
}

story::Story told(const std::string& name) { return story::tell(test::fixture(name), test::config(), "pt"); }

// Post-planning rules for a hand-made plan, so a rule can be tested on facts the planner did not pick.
std::vector<Caveat> post_rules_for(const std::string& name, std::vector<std::vector<std::string>> paragraphs) {
    const auto payload = test::fixture(name);
    auto facts = story::extract_facts(payload, test::config().params);
    story::apply_pre_rules(payload, test::config(), facts);
    story::Plan plan;
    plan.paragraphs = std::move(paragraphs);
    return story::apply_post_rules(payload, test::config(), facts, plan);
}

}  // namespace

TEST_CASE("C01: referral hospitals are described as hubs") {
    CHECK(has(all_caveats(told("hc_1000")), "C01", "self"));
    CHECK_FALSE(has(all_caveats(told("butanta_1000")), "C01"));

    auto payload = test::fixture("butanta_1000");
    payload.surroundings["facilities"].push_back(
        {{"type", "Hospital Geral"}, {"beds", 120}, {"sus_network", true}, {"distance_m", 400}});
    const auto s = story::tell(payload, test::config(), "pt");
    CHECK(has(s.plan.caveats, "C01", "nearby"));
    const auto& around = s.plan.paragraphs[story::kSurroundings];
    CHECK(std::find(around.begin(), around.end(), "network") != around.end());
}

TEST_CASE("C03b: imprecise estimates are disclosed") {
    CHECK(has(told("padeiros_1000").plan.caveats, "C03b"));
    CHECK_FALSE(has(told("butanta_1000").plan.caveats, "C03b"));
}

TEST_CASE("C04: off-network sewage says what households use instead") {
    CHECK(has(told("padeiros_1000").plan.caveats, "C04", "precarious"));
    CHECK_FALSE(has(post_rules_for("butanta_1000", {{}, {}, {"sewage"}, {}}), "C04"));  // 0.6% off the network
}

TEST_CASE("C06: private capacity without SUS is pointed out") {
    CHECK(has(post_rules_for("butanta_1000", {{}, {}, {"network"}, {}}), "C06"));
    CHECK_FALSE(has(post_rules_for("padeiros_1000", {{}, {}, {"network"}, {}}), "C06"));  // no other facility
}

TEST_CASE("C10: the bridge names the scales that follow") {
    CHECK(has(told("hc_1000").plan.caveats, "C10", "district"));
    CHECK(has(told("padeiros_1000").plan.caveats, "C10", ""));
    CHECK(has(post_rules_for("butanta_1000", {{}, {}, {}, {"tb_district", "dengue"}}), "C10", "district_municipality"));
}

TEST_CASE("C12: an earlier epidemic year is disclosed") {
    CHECK(has(told("padeiros_1000").plan.caveats, "C12", ""));
}

TEST_CASE("C14: no 'far from primary care' figure around a public primary care unit") {
    CHECK(has(told("padeiros_1000").suppressed, "C14"));
    CHECK(story::find_fact(told("padeiros_1000").facts, "access") == nullptr);
    CHECK_FALSE(has(told("poa_1000").suppressed, "C14"));  // a polyclinic
}

TEST_CASE("C14b: poor public access among private services is put in context") {
    CHECK(has(told("hc_1000").plan.caveats, "C14b"));
    CHECK_FALSE(has(post_rules_for("poa_1000", {{}, {}, {"access"}, {}}), "C14b"));  // access similar to the municipality
}

TEST_CASE("C15: small counts are told as counts") {
    const auto s = told("padeiros_1000");
    const auto* lepto = story::find_fact(s.facts, "lepto");
    REQUIRE(lepto != nullptr);
    CHECK(lepto->variant == "small");
    CHECK_FALSE(lepto->tier.has_value());
    const auto* tb = story::find_fact(told("butanta_1000").facts, "tb_district");
    CHECK(tb->variant != "small");
}

TEST_CASE("C17: district and municipal sources are told apart") {
    CHECK(has(post_rules_for("butanta_1000", {{}, {}, {}, {"tb_district", "dengue"}}), "C17"));
    CHECK_FALSE(has(post_rules_for("butanta_1000", {{}, {}, {}, {"tb_district", "teen_district"}}), "C17"));
}

TEST_CASE("C18b: a profile with many ill-defined deaths is flagged") {
    CHECK(has(post_rules_for("poa_1000", {{}, {}, {}, {"mortality"}}), "C18b"));
    CHECK_FALSE(has(post_rules_for("padeiros_1000", {{}, {}, {}, {"mortality"}}), "C18b"));
}

TEST_CASE("C19: a district outside the model's range is told with the model's limits") {
    auto payload = test::fixture("butanta_1000");
    for (auto& row : payload.expected) {
        if (row.value("outcome", "") == "tb" && row.value("scale", "") == "district") row["flag"] = "above";
    }
    const auto s = story::tell(payload, test::config(), "pt");
    REQUIRE(story::find_fact(s.facts, "surprise_tb") != nullptr);
    CHECK(has(s.plan.caveats, "C19"));
    CHECK(s.plan.paragraphs[story::kLead] == std::vector<std::string>{"surprise_tb"});
}

namespace {

// Need and supply for Padeiros as the 1 km radius tells them: few residents per unit, high need.
story::Payload radius_fallback(double population, int territory_type) {
    auto payload = test::fixture("padeiros_1000");
    auto& ctx = payload.context;
    ctx["supply_measure"] = "radius";
    ctx["territory_type"] = territory_type;
    ctx["values"]["deprived"] = 100.0;
    ctx["values"]["load"] = population;
    ctx["values"]["population"] = population;
    ctx["need_percentile"] = 0.99;
    ctx["load_percentile"] = 0.02;
    return payload;
}

// The same unit on the catchment model, with high need and few people per unit, and no registered team.
story::Payload catchment(bool near_edge) {
    auto payload = test::fixture("padeiros_1000");
    auto& ctx = payload.context;
    ctx.erase("team_equivalents");
    for (const char* key : {"served_per_team", "served_mean_distance", "served_far"}) ctx["values"].erase(key);
    ctx["supply_measure"] = "catchment";
    ctx["values"]["served"] = 3000.0;
    ctx["values"]["served_deprived"] = 95.0;
    ctx["need_percentile"] = 0.99;
    ctx["load_percentile"] = 0.05;
    ctx["near_edge"] = near_edge;
    return payload;
}

// The catchment model with teams: people per team against the PNAB range, and the distance.
story::Payload with_teams(double per_team, double mean_distance) {
    auto payload = catchment(false);
    auto& ctx = payload.context;
    ctx["team_equivalents"] = 2.0;
    ctx["values"]["served_per_team"] = per_team;
    ctx["values"]["served_mean_distance"] = mean_distance;
    ctx["values"]["served_far"] = mean_distance > 2000 ? 60.0 : 5.0;
    return payload;
}

}  // namespace

TEST_CASE("need against supply is read against the PNAB range of people per team") {
    const auto variant = [](double per_team) {
        const auto s = story::tell(with_teams(per_team, 800), test::config(), "pt");
        const auto* need = story::find_fact(s.facts, "need_supply");
        REQUIRE(need != nullptr);
        REQUIRE(need->tier.has_value());
        return std::make_pair(need->variant, *need->tier);
    };
    CHECK(variant(4300) == std::make_pair(std::string("above"), story::Tier::Higher));
    CHECK(variant(2800) == std::make_pair(std::string("within"), story::Tier::Similar));
    CHECK(variant(1500) == std::make_pair(std::string("below"), story::Tier::Lower));
    // without a registered team the unit is ranked by people per unit, with no PNAB comparison
    const auto none = story::tell(catchment(false), test::config(), "pt");
    CHECK(story::find_fact(none.facts, "need_supply")->variant == "served");
    CHECK_FALSE(story::find_fact(none.facts, "need_supply")->tier.has_value());
}

TEST_CASE("C22: the distance is told when the catchment lives far from the unit") {
    CHECK(has(story::tell(with_teams(1500, 4100), test::config(), "pt").plan.caveats, "C22"));
    CHECK_FALSE(has(story::tell(with_teams(1500, 800), test::config(), "pt").plan.caveats, "C22"));
    CHECK_FALSE(has(story::tell(catchment(false), test::config(), "pt").plan.caveats, "C22"));  // no distance figure
}

TEST_CASE("every need-against-supply variant is told and verified in both languages") {
    for (auto payload : {with_teams(4300, 800), with_teams(2800, 3500), with_teams(1500, 4100)}) {
        for (const char* code : {"pt", "en"}) {
            const auto body = story::narrate(payload, test::config(), code);
            INFO(code << " " << body.at("issues").dump());
            CHECK(body.at("verified").get<bool>());
        }
    }
}

TEST_CASE("C20: peer comparisons only at the reference radius") {
    auto payload = radius_fallback(169, 1);
    payload.surroundings["radius_m"] = 2000;
    const auto s = story::tell(payload, test::config(), "pt");
    CHECK(has(s.suppressed, "C20"));
    CHECK(story::find_fact(s.facts, "peer") == nullptr);
    CHECK(story::find_fact(s.facts, "need_supply") == nullptr);
    CHECK_FALSE(has(told("padeiros_1000").suppressed, "C20"));
}

TEST_CASE("C20: need and supply on the catchment do not depend on the radius") {
    auto payload = catchment(false);
    payload.surroundings["radius_m"] = 2000;
    const auto s = story::tell(payload, test::config(), "pt");
    CHECK(has(s.suppressed, "C20"));  // peer and territory still go
    CHECK(story::find_fact(s.facts, "peer") == nullptr);
    const auto* need = story::find_fact(s.facts, "need_supply");
    REQUIRE(need != nullptr);
    CHECK(need->variant == "served");
    CHECK(need->slots.count("served_catchment"));
}

TEST_CASE("C21: without the catchment, few residents per unit in sparse surroundings is not spare capacity") {
    const auto sparse = story::tell(radius_fallback(169, 1), test::config(), "pt");
    CHECK(story::find_fact(sparse.facts, "need_supply")->variant == "sparse_radius");
    CHECK(has(sparse.plan.caveats, "C21"));
    CHECK(story::find_fact(story::tell(radius_fallback(3000, 2), test::config(), "pt").facts, "need_supply")->variant ==
          "sparse_radius");  // populated below the threshold

    const auto dense = story::tell(radius_fallback(30000, 3), test::config(), "pt");
    CHECK(story::find_fact(dense.facts, "need_supply")->variant == "served_radius");
    CHECK_FALSE(has(dense.plan.caveats, "C21"));
    CHECK_FALSE(has(story::tell(catchment(false), test::config(), "pt").plan.caveats, "C21"));
}

TEST_CASE("C21b: a catchment near the region's edge is disclosed") {
    const auto edge = story::tell(catchment(true), test::config(), "pt");
    REQUIRE(story::find_fact(edge.facts, "need_supply") != nullptr);
    CHECK(has(edge.plan.caveats, "C21b"));
    CHECK_FALSE(has(story::tell(catchment(false), test::config(), "pt").plan.caveats, "C21b"));
}

TEST_CASE("need and supply are told and verified on both measures") {
    for (auto payload : {radius_fallback(169, 1), radius_fallback(30000, 3), catchment(false), catchment(true)}) {
        for (const char* code : {"pt", "en"}) {
            const auto body = story::narrate(payload, test::config(), code);
            INFO(code << " " << body.at("issues").dump());
            CHECK(body.at("verified").get<bool>());
        }
    }
}

TEST_CASE("caveats only attach to planned facts") {
    for (const char* name : test::kFixtures) {
        const auto s = told(name);
        for (const auto& c : s.plan.caveats) {
            const bool planned = std::any_of(s.plan.paragraphs.begin(), s.plan.paragraphs.end(), [&](const auto& p) {
                return std::find(p.begin(), p.end(), c.fact) != p.end();
            });
            CHECK(planned);
        }
    }
}

namespace {

// Hospital das Clínicas with in-hospital death figures of the given band.
story::Payload with_deaths(const std::string& band, double admissions = 20000, double deaths = 1100,
                           double expected = 1000) {
    auto payload = test::fixture("hc_1000");
    payload.facility["internacoes_total"] = admissions;
    payload.facility["obitos_sus"] = deaths;
    payload.facility["obitos_esperados"] = expected;
    payload.facility["mortalidade_faixa"] = band;
    return payload;
}

}  // namespace

TEST_CASE("in-hospital deaths are told against the case mix, never alone") {
    const auto s = story::tell(with_deaths("within"), test::config(), "pt");
    const auto* deaths = story::find_fact(s.facts, "deaths");
    REQUIRE(deaths != nullptr);
    CHECK(deaths->tier == story::Tier::Similar);
    CHECK(deaths->slots.at("rate_unit").number == Approx(5.5));
    CHECK(deaths->slots.at("expected_unit").number == Approx(5.0));
    const auto& unit = s.plan.paragraphs[story::kUnit];
    const auto at = [&](const char* id) { return std::find(unit.begin(), unit.end(), id) - unit.begin(); };
    REQUIRE(at("deaths") < static_cast<long>(unit.size()));
    CHECK(at("admissions") + 1 == at("deaths"));  // the case mix comes first
    CHECK(story::find_fact(s.facts, "admissions")->mandatory);
    CHECK(has(s.plan.caveats, "C23"));
    CHECK_FALSE(has(s.plan.caveats, "C23b"));
    CHECK_FALSE(has(s.plan.caveats, "C23c"));
}

TEST_CASE("C23b and C23c: deaths outside the range are put in context in their direction") {
    const auto below = story::tell(with_deaths("below", 20000, 40, 1000), test::config(), "pt");
    CHECK(story::find_fact(below.facts, "deaths")->tier == story::Tier::Lower);
    CHECK(has(below.plan.caveats, "C23b"));
    CHECK_FALSE(has(below.plan.caveats, "C23c"));
    const auto above = story::tell(with_deaths("above", 20000, 3000, 1000), test::config(), "pt");
    CHECK(story::find_fact(above.facts, "deaths")->tier == story::Tier::Higher);
    CHECK(has(above.plan.caveats, "C23c"));
    CHECK_FALSE(has(above.plan.caveats, "C23b"));
}

TEST_CASE("C24: few admissions or few expected deaths suppress the death rate") {
    const auto few_admissions = story::tell(with_deaths("within", 80, 4, 6), test::config(), "pt");
    CHECK(story::find_fact(few_admissions.facts, "deaths") == nullptr);
    CHECK(has(few_admissions.suppressed, "C24", "admissions"));
    CHECK_FALSE(story::find_fact(few_admissions.facts, "admissions")->mandatory);
    const auto few_expected = story::tell(with_deaths("within", 3000, 2, 3), test::config(), "pt");
    CHECK(has(few_expected.suppressed, "C24", "expected"));
    // at the thresholds the rate is told
    CHECK(story::find_fact(story::tell(with_deaths("within", 100, 6, 5), test::config(), "pt").facts, "deaths"));
}

TEST_CASE("no death rate without SUS admissions or without the case-mix figures") {
    CHECK(story::find_fact(told("hc_1000").facts, "deaths") == nullptr);  // fixture without the figures
    auto payload = with_deaths("within");
    payload.facility.erase("mortalidade_faixa");
    CHECK(story::find_fact(story::tell(payload, test::config(), "pt").facts, "deaths") == nullptr);
    CHECK(story::find_fact(story::tell(with_deaths("within", 0, 0, 0), test::config(), "pt").facts, "deaths") == nullptr);
}

TEST_CASE("every in-hospital death variant is told and verified in both languages") {
    for (auto payload : {with_deaths("within"), with_deaths("below", 20000, 40, 1000), with_deaths("above", 20000, 3000, 1000)}) {
        for (const char* code : {"pt", "en"}) {
            const auto body = story::narrate(payload, test::config(), code);
            INFO(code << " " << body.at("issues").dump());
            CHECK(body.at("verified").get<bool>());
            const auto text = body.at("text").get<std::string>();
            CHECK(text.find(code == std::string("pt") ? "não mede a qualidade" : "does not measure the quality") != std::string::npos);
        }
    }
}

namespace {

// The composition behind the expected rate (database/reference/compute_hospital_mortality.py), with
// the Shapley parts in percentage points: diagnosis, age, admission type.
nlohmann::json mix(double diagnosis, double age, double urgency, double urgent_pct = 70) {
    return {{"taxa_regiao", 5.16},
            {"shapley_pp", {{"diagnostico", diagnosis}, {"idade", age}, {"carater", urgency}}},
            {"idosos_pct", 61.7}, {"idosos_regiao_pct", 16.7},
            {"urgencia_pct", urgent_pct}, {"urgencia_regiao_pct", 68.7},
            {"capitulo", "internacoes_infecciosas_parasitarias"}, {"capitulo_pct", 13.6},
            {"capitulo_regiao_pct", 4.6}, {"capitulo_taxa_regiao", 27.53}};
}

// 22% expected (above the regional 5.16%) or 2.5% (below), with the given composition.
story::Payload with_mix(const nlohmann::json& profile, bool up = true, const std::string& band = "within",
                        const std::string& flow = "Atendimento de Demanda Espontânea e Referenciada") {
    auto payload = with_deaths(band, 20000, up ? 4600 : 600, up ? 4400 : 500);
    payload.facility["mortalidade_perfil"] = profile;
    payload.facility["Fluxo_Clientela"] = flow;
    return payload;
}

}  // namespace

TEST_CASE("the expected rate is explained by the factors that move it most") {
    const auto s = story::tell(with_mix(mix(7.9, 7.4, 1.9)), test::config(), "pt");
    const auto* f = story::find_fact(s.facts, "casemix");
    REQUIRE(f != nullptr);
    CHECK(f->variant == "diagnosis_age.up");  // the second weighs more than half the first
    CHECK(f->tier == story::Tier::Higher);
    CHECK(f->slots.at("rate_region").number == Approx(5.16));
    CHECK(f->slots.count("chapter_share_unit"));
    CHECK(f->slots.count("old_share_unit"));
    CHECK_FALSE(f->slots.count("urgent_share_unit"));
    const auto& unit = s.plan.paragraphs[story::kUnit];
    const auto deaths = std::find(unit.begin(), unit.end(), "deaths");
    REQUIRE(deaths != unit.end());
    CHECK(*(deaths + 1) == "casemix");
    CHECK(has(s.plan.caveats, "C23"));
    CHECK(std::find_if(s.plan.caveats.begin(), s.plan.caveats.end(), [](const auto& c) {
              return c.rule == "C23" && c.fact == "casemix";
          }) != s.plan.caveats.end());  // the caveats follow the explanation

    CHECK(story::find_fact(story::tell(with_mix(mix(1, 8, 0.5)), test::config(), "pt").facts, "casemix")->variant == "age.up");
    CHECK(story::find_fact(story::tell(with_mix(mix(0.4, 0.5, -3.5), false), test::config(), "pt").facts, "casemix")->variant ==
          "urgency.down");
}

TEST_CASE("no explanation when no factor moves the expected rate much") {
    // one factor must move it by half the regional rate (2.58 points)
    CHECK(story::find_fact(story::tell(with_mix(mix(2.5, 1, 0.5)), test::config(), "pt").facts, "casemix") == nullptr);
    CHECK(story::find_fact(story::tell(with_deaths("within"), test::config(), "pt").facts, "casemix") == nullptr);  // no profile
}

TEST_CASE("C24 suppresses the explanation with the death rate") {
    auto payload = with_mix(mix(7.9, 7.4, 1.9));
    payload.facility["internacoes_total"] = 80;
    const auto s = story::tell(payload, test::config(), "pt");
    CHECK(story::find_fact(s.facts, "casemix") == nullptr);
    CHECK(has(s.suppressed, "C24", "admissions"));
}

TEST_CASE("C23d: referred patients recorded as elective lower the expected rate") {
    const auto referred = "Atendimento de Demanda Referenciada";
    CHECK(has(story::tell(with_mix(mix(0.4, 0.5, -3.5, 3), false, "above", referred), test::config(), "pt").plan.caveats, "C23d"));
    // walk-in patients too, or most admissions urgent: the coding is plausible
    CHECK_FALSE(has(story::tell(with_mix(mix(0.4, 0.5, -3.5, 3), false, "above"), test::config(), "pt").plan.caveats, "C23d"));
    CHECK_FALSE(has(story::tell(with_mix(mix(0.4, 0.5, -3.5, 30), false, "above", referred), test::config(), "pt").plan.caveats, "C23d"));
    // the admission type raising the expected rate is not a coding problem
    CHECK_FALSE(has(story::tell(with_mix(mix(0.5, 1, 8, 3), true, "within", referred), test::config(), "pt").plan.caveats, "C23d"));
}

TEST_CASE("every explanation of the expected rate is told and verified in both languages") {
    const std::vector<std::array<double, 3>> parts{{8, 1, 0.5}, {1, 8, 0.5}, {0.5, 1, 8}, {8, 7, 0.5}, {8, 0.5, 7}, {0.5, 8, 7}};
    for (const auto& p : parts) {
        for (bool up : {true, false}) {
            const double sign = up ? 1 : -1;
            const auto payload = with_mix(mix(sign * p[0], sign * p[1], sign * p[2], 3), up, up ? "within" : "above",
                                          "Atendimento de Demanda Referenciada");
            for (const char* code : {"pt", "en"}) {
                const auto body = story::narrate(payload, test::config(), code);
                INFO(code << " " << p[0] << " " << p[1] << " " << p[2] << " " << up << " " << body.at("issues").dump());
                CHECK(body.at("verified").get<bool>());
                const auto& plan = body.at("plan").at(story::kUnit);
                CHECK(std::find(plan.begin(), plan.end(), "casemix") != plan.end());
            }
        }
    }
}

TEST_CASE("no admission at 70 or more is said in words, not as 0.0%") {
    for (const auto& [parts, variant] : std::vector<std::pair<std::array<double, 3>, std::string>>{
             {{-1, -8, -0.5}, "age0.down"}, {{-8, -7, -0.5}, "diagnosis_age0.down"}, {{-0.5, -8, -7}, "age0_urgency.down"}}) {
        auto profile = mix(parts[0], parts[1], parts[2]);
        profile["idosos_pct"] = 0;
        const auto payload = with_mix(profile, false);
        CHECK(story::find_fact(story::tell(payload, test::config(), "pt").facts, "casemix")->variant == variant);
        for (const char* code : {"pt", "en"}) {
            const auto body = story::narrate(payload, test::config(), code);
            INFO(code << " " << variant << " " << body.at("issues").dump());
            CHECK(body.at("verified").get<bool>());
            int told = 0;
            for (const auto& paragraph : body.at("paragraphs")) {
                for (const auto& sentence : paragraph) {
                    const auto& facts = sentence.at("facts");
                    if (std::find(facts.begin(), facts.end(), "casemix") == facts.end()) continue;
                    std::string text;
                    for (const auto& segment : sentence.at("segments")) text += segment.at("text").get<std::string>();
                    CHECK(text.find(code == std::string("pt") ? " 0,0%" : " 0.0%") == std::string::npos);
                    CHECK(text.find(code == std::string("pt") ? "nenhum" : " no") != std::string::npos);
                    ++told;
                }
            }
            CHECK(told == 1);
        }
    }
}
