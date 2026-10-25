#include <catch2/catch_test_macros.hpp>

#include "helpers.hpp"
#include "story/narrative.hpp"

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
    REQUIRE(s.plan.paragraphs.size() == 3);
    CHECK(s.plan.paragraphs[0].front() == "profile");
    CHECK(s.plan.paragraphs[1].front() == "residents");
    CHECK(s.plan.paragraphs[2].front() == "tb_district");  // district before municipality
}
