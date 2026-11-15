#include <algorithm>

#include <catch2/catch_test_macros.hpp>

#include "helpers.hpp"
#include "story/caveats.hpp"
#include "story/facts.hpp"
#include "story/narrative.hpp"
#include "story/planner.hpp"

namespace {

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
    CHECK(has(told("butanta_1000").plan.caveats, "C06"));
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

// The same unit on the catchment model, with high need and few people per unit.
story::Payload catchment(bool near_edge) {
    auto payload = test::fixture("padeiros_1000");
    auto& ctx = payload.context;
    ctx["supply_measure"] = "catchment";
    ctx["values"]["served"] = 3000.0;
    ctx["values"]["served_deprived"] = 95.0;
    ctx["need_percentile"] = 0.99;
    ctx["load_percentile"] = 0.05;
    ctx["near_edge"] = near_edge;
    return payload;
}

}  // namespace

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
