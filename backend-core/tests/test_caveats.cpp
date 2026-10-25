#include <algorithm>

#include <catch2/catch_test_macros.hpp>

#include "helpers.hpp"
#include "story/caveats.hpp"
#include "story/facts.hpp"
#include "story/narrative.hpp"

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
    CHECK(std::find(s.plan.paragraphs[1].begin(), s.plan.paragraphs[1].end(), "network") != s.plan.paragraphs[1].end());
}

TEST_CASE("C03b: imprecise estimates are disclosed") {
    CHECK(has(told("padeiros_1000").plan.caveats, "C03b"));
    CHECK_FALSE(has(told("butanta_1000").plan.caveats, "C03b"));
}

TEST_CASE("C04: off-network sewage says what households use instead") {
    CHECK(has(told("padeiros_1000").plan.caveats, "C04", "precarious"));
    CHECK_FALSE(has(post_rules_for("butanta_1000", {{}, {"sewage"}, {}}), "C04"));  // 0.6% off the network
}

TEST_CASE("C06: private capacity without SUS is pointed out") {
    CHECK(has(told("butanta_1000").plan.caveats, "C06"));
    CHECK_FALSE(has(post_rules_for("padeiros_1000", {{}, {"network"}, {}}), "C06"));  // no other facility
}

TEST_CASE("C10: the bridge names the scales that follow") {
    CHECK(has(told("hc_1000").plan.caveats, "C10", "district"));
    CHECK(has(told("padeiros_1000").plan.caveats, "C10", ""));
    CHECK(has(post_rules_for("butanta_1000", {{}, {}, {"tb_district", "dengue"}}), "C10", "district_municipality"));
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
    CHECK_FALSE(has(post_rules_for("poa_1000", {{}, {"access"}, {}}), "C14b"));  // access similar to the municipality
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
    CHECK(has(post_rules_for("butanta_1000", {{}, {}, {"tb_district", "dengue"}}), "C17"));
    CHECK_FALSE(has(post_rules_for("butanta_1000", {{}, {}, {"tb_district", "teen_district"}}), "C17"));
}

TEST_CASE("C18b: a profile with many ill-defined deaths is flagged") {
    CHECK(has(post_rules_for("poa_1000", {{}, {}, {"mortality"}}), "C18b"));
    CHECK_FALSE(has(post_rules_for("padeiros_1000", {{}, {}, {"mortality"}}), "C18b"));
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
