#include <algorithm>

#include <catch2/catch_test_macros.hpp>

#include "helpers.hpp"
#include "story/narrative.hpp"
#include "story/planner.hpp"

TEST_CASE("every fixture is told and verified in both languages") {
    for (const char* name : test::kFixtures) {
        for (const char* code : {"pt", "en"}) {
            const auto body = story::narrate(test::fixture(name), test::config(), code);
            INFO(name << " " << code << " " << body.at("issues").dump());
            CHECK(body.at("verified").get<bool>());
            const auto text = body.at("text").get<std::string>();
            CHECK(text.find('{') == std::string::npos);
            CHECK(text.find("<pl:") == std::string::npos);
            CHECK(text.find("<cmp>") == std::string::npos);
        }
    }
}

TEST_CASE("Portuguese and English tell the same facts") {
    for (const char* name : test::kFixtures) {
        const auto pt = story::tell(test::fixture(name), test::config(), "pt");
        const auto en = story::tell(test::fixture(name), test::config(), "en");
        CHECK(pt.plan.paragraphs == en.plan.paragraphs);
    }
}

TEST_CASE("slots carry their scale to the page") {
    const auto body = story::narrate(test::fixture("butanta_1000"), test::config(), "pt");
    bool district = false, city = false;
    for (const auto& paragraph : body.at("paragraphs")) {
        for (const auto& sentence : paragraph) {
            for (const auto& segment : sentence.at("segments")) {
                if (segment.value("text", "") == "52,7") district = segment.value("scope", "") == "district";
                if (segment.value("text", "") == "72,6") city = segment.value("scope", "") == "city";
            }
        }
    }
    CHECK(district);
    CHECK(city);
}

TEST_CASE("the schema orders the narrative from unit to surroundings to outcomes") {
    const auto s = story::tell(test::fixture("butanta_1000"), test::config(), "pt");
    REQUIRE(s.plan.paragraphs.size() == 4);
    CHECK(s.plan.paragraphs[story::kLead] == std::vector<std::string>{"peer"});
    CHECK(s.plan.paragraphs[story::kUnit].front() == "profile");
    CHECK(s.plan.paragraphs[story::kSurroundings].front() == "residents");
    CHECK(s.plan.paragraphs[story::kOutcomes].front() == "tb_district");  // district before municipality
}

TEST_CASE("the lead is the strongest comparison, and it is not repeated") {
    const auto s = story::tell(test::fixture("padeiros_1000"), test::config(), "pt");
    CHECK(s.plan.paragraphs[story::kLead] == std::vector<std::string>{"need_supply"});
    const auto* peer = story::find_fact(s.facts, "peer");
    REQUIRE(peer != nullptr);
    CHECK(peer->slots.at("indicator").text.find("deprived") == std::string::npos);
    const auto* need = story::find_fact(s.facts, "need_supply");
    CHECK(need->variant == "below");  // high need, fewer people per team than the PNAB range
    CHECK(need->slots.count("served_catchment"));  // told on the catchment, not the 1 km circle
    const auto has_rule = [&](const char* rule) {
        return std::any_of(s.plan.caveats.begin(), s.plan.caveats.end(), [&](const story::Caveat& c) { return c.rule == rule; });
    };
    CHECK(has_rule("C21b"));  // near the RMSP edge
    CHECK(has_rule("C22"));   // its residents live 2.6 km away on average
    CHECK(story::find_fact(s.facts, "territory")->slots.at("type").text == "territory:1");
}

TEST_CASE("the lead depends on the facility's role") {
    // a referral hospital serves the region: the text starts with the unit itself
    const auto hub = story::tell(test::fixture("hc_1000"), test::config(), "pt");
    CHECK(hub.plan.paragraphs[story::kLead].empty());
    CHECK(hub.plan.paragraphs[story::kUnit].front() == "profile");
    // a specialised service is not led by district outcomes, only by its peer rank
    auto payload = test::fixture("poa_1000");
    for (auto& row : payload.expected) row["flag"] = "above";
    const auto specialised = story::tell(payload, test::config(), "pt");
    for (const auto& id : specialised.plan.paragraphs[story::kLead]) CHECK(id == "peer");
    // a primary care unit can be led by them
    auto ubs = test::fixture("butanta_1000");
    for (auto& row : ubs.expected) {
        if (row.value("outcome", "") == "tb" && row.value("scale", "") == "district") row["flag"] = "above";
    }
    CHECK(story::tell(ubs, test::config(), "pt").plan.paragraphs[story::kLead] == std::vector<std::string>{"surprise_tb"});
}

TEST_CASE("neighbouring facts are joined by the relation between them") {
    const auto text = story::narrate(test::fixture("butanta_1000"), test::config(), "pt").at("text").get<std::string>();
    CHECK(text.find("Além disso, 0,6% dos domicílios") != std::string::npos);  // two indicators better than the city
}

TEST_CASE("a text that fails verification is not served") {
    auto strict = test::config();
    strict.languages.at("pt").max_words = 5;
    const auto withheld = story::servable(story::narrate(test::fixture("padeiros_1000"), strict, "pt"));
    CHECK(withheld.at("withheld").get<bool>());
    CHECK_FALSE(withheld.contains("paragraphs"));
    CHECK_FALSE(withheld.contains("text"));
    CHECK(withheld.contains("facts"));

    const auto served = story::servable(story::narrate(test::fixture("padeiros_1000"), test::config(), "pt"));
    CHECK_FALSE(served.contains("withheld"));
    CHECK(served.contains("paragraphs"));
}

TEST_CASE("the response carries the peer comparison the text cites") {
    const auto body = story::narrate(test::fixture("padeiros_1000"), test::config(), "pt");
    const auto& reference = body.at("reference");
    REQUIRE(reference.is_object());
    CHECK(reference.at("radius").get<int>() == 1000);
    CHECK(reference.at("percentiles").contains("deprived"));
    CHECK(reference.contains("need_percentile"));
}

TEST_CASE("the territorial type stays on its card, out of the text") {
    for (const char* name : test::kFixtures) {
        const auto s = story::tell(test::fixture(name), test::config(), "pt");
        for (const auto& paragraph : s.plan.paragraphs) {
            CHECK(std::find(paragraph.begin(), paragraph.end(), "territory") == paragraph.end());
        }
    }
}
