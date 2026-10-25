#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include "helpers.hpp"
#include "story/facts.hpp"

using Catch::Approx;
using story::Tier;

namespace {

const story::Fact& fact(const std::vector<story::Fact>& facts, const std::string& id) {
    const auto* f = story::find_fact(facts, id);
    REQUIRE(f != nullptr);
    return *f;
}

double value(const story::Fact& f, const std::string& field) { return f.slots.at(field).number; }

}  // namespace

TEST_CASE("comparisons map onto fixed lexical tiers") {
    const auto& p = test::config().params;
    CHECK(story::compare(66.8, 66.0, true, p).tier == Tier::Similar);   // under 2 points
    CHECK(story::compare(10.0, 9.5, false, p).tier == Tier::Similar);   // under 10%
    CHECK(story::compare(13.0, 10.0, false, p).tier == Tier::Higher);
    CHECK(story::compare(17.0, 10.0, false, p).tier == Tier::MuchHigher);
    const auto times = story::compare(30.0, 10.0, false, p);
    CHECK(times.tier == Tier::TimesHigher);
    CHECK(times.ratio == Approx(3.0));
    CHECK(story::compare(8.0, 10.0, false, p).tier == Tier::Lower);
    CHECK(story::compare(4.0, 10.0, false, p).tier == Tier::MuchLower);
    CHECK(story::compare(5.0, 0.0, false, p).tier == Tier::MuchHigher);  // no ratio without a reference
    CHECK(story::compare(0.0, 0.0, false, p).tier == Tier::Similar);
}

TEST_CASE("salience saturates and treats shares by absolute difference") {
    const auto& p = test::config().params;
    CHECK(story::compare(90.6, 66.8, true, p).salience == Approx(1.0));
    CHECK(story::compare(0.6, 4.8, true, p).salience == Approx(0.42));
    CHECK(story::compare(30.0, 10.0, false, p).salience == Approx(1.0));
    CHECK(story::compare(10.0, 10.0, false, p).salience == Approx(0.0));
}

// The values below were checked on the facility page in the browser.
TEST_CASE("facts carry the same figures as the cards") {
    const auto& p = test::config().params;

    const auto padeiros = story::extract_facts(test::fixture("padeiros_1000"), p);
    const auto& sewage = fact(padeiros, "sewage");
    CHECK(value(sewage, "radius") == Approx(90.6));
    CHECK(value(sewage, "municipality") == Approx(66.8));
    CHECK(value(sewage, "region") == Approx(8.3));
    CHECK(value(sewage, "precarious_radius") == Approx(60.3));

    const auto butanta = story::extract_facts(test::fixture("butanta_1000"), p);
    CHECK(value(fact(butanta, "tb_district"), "district") == Approx(52.7).margin(0.05));
    CHECK(value(fact(butanta, "tb_district"), "city") == Approx(72.6).margin(0.05));
    CHECK(value(fact(butanta, "teen_district"), "district") == Approx(3.2).margin(0.05));
    CHECK(value(fact(butanta, "teen_district"), "city") == Approx(7.4).margin(0.05));

    const auto poa = story::extract_facts(test::fixture("poa_1000"), p);
    CHECK(value(fact(poa, "mortality"), "ill_defined_municipality") == Approx(26.3).margin(0.05));

    const auto hc = story::extract_facts(test::fixture("hc_1000"), p);
    CHECK(value(fact(hc, "beds"), "unit") == 1543);
}

TEST_CASE("unit facts follow the facility's type and position") {
    const auto& p = test::config().params;
    const auto hc = story::extract_facts(test::fixture("hc_1000"), p);
    CHECK(story::find_fact(hc, "beds") != nullptr);
    CHECK(story::find_fact(hc, "staff") == nullptr);
    CHECK(story::find_fact(hc, "admissions") != nullptr);
    CHECK(story::find_fact(hc, "position") == nullptr);  // corrected by 200 m, under the 500 m threshold

    const auto padeiros = story::extract_facts(test::fixture("padeiros_1000"), p);
    CHECK(fact(padeiros, "position").variant == "corrected");
    CHECK(story::find_fact(padeiros, "tb_district") == nullptr);
}

TEST_CASE("radius coverage measures how much of the tracts lies inside the circle") {
    CHECK(story::radius_coverage(test::fixture("padeiros_1000")) < 0.5);
    CHECK(story::radius_coverage(test::fixture("butanta_1000")) > 0.5);
}
