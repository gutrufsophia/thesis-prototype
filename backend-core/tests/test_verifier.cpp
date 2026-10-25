#include <algorithm>

#include <catch2/catch_test_macros.hpp>

#include "helpers.hpp"
#include "story/mutation.hpp"
#include "story/narrative.hpp"
#include "story/realiser.hpp"
#include "story/verifier.hpp"

namespace {

bool flags(const std::vector<story::Issue>& issues, const std::string& check) {
    return std::any_of(issues.begin(), issues.end(), [&](const story::Issue& i) { return i.check == check; });
}

struct Case {
    story::Story story;
    const story::Language* lang;
};

Case told(const std::string& name, const std::string& code) {
    return {story::tell(test::fixture(name), test::config(), code), &test::config().language(code)};
}

std::vector<story::Issue> check_sentence(Case& c, int pi, int si, const std::string& text) {
    auto paragraphs = c.story.paragraphs;
    paragraphs[pi][si].text = text;
    return story::verify(paragraphs, c.story.plan, c.story.facts, *c.lang);
}

}  // namespace

TEST_CASE("realisations from templates pass every check") {
    for (const char* name : test::kFixtures) {
        for (const char* code : {"pt", "en"}) {
            auto c = told(name, code);
            const auto issues = story::verify(c.story.paragraphs, c.story.plan, c.story.facts, *c.lang);
            INFO(name << " " << code << " " << story::to_json(issues).dump());
            CHECK(issues.empty());
        }
    }
}

TEST_CASE("every planted error is caught") {
    for (const char* name : test::kFixtures) {
        for (const char* code : {"pt", "en"}) {
            auto c = told(name, code);
            const auto mutants = story::mutate(c.story.paragraphs, c.story.plan, c.story.facts, *c.lang);
            CHECK(mutants.size() > 30);
            for (const auto& m : mutants) {
                INFO(name << " " << code << " " << m.op << " " << m.detail);
                CHECK_FALSE(story::verify(m.paragraphs, c.story.plan, c.story.facts, *c.lang).empty());
            }
        }
    }
}

TEST_CASE("V1 and V5 on hand-written sentences") {
    auto c = told("padeiros_1000", "pt");
    // paragraph 1, sentence 2 is the sewage contrast
    const auto& original = c.story.paragraphs[1][2].text;
    REQUIRE(original.find("{sewage.radius}") != std::string::npos);

    CHECK(flags(check_sentence(c, 1, 2, original + " Em 2023 foram 90,6%."), "V1"));

    std::string wrong_scale = original;
    wrong_scale.replace(wrong_scale.find("do raio"), 7, "do município");
    CHECK(flags(check_sentence(c, 1, 2, wrong_scale), "V5"));

    std::string swapped = original;
    swapped.replace(swapped.find("{sewage.radius}"), 15, "{sewage.region}");
    CHECK(flags(check_sentence(c, 1, 2, swapped), "V5"));
}

TEST_CASE("V6 and V7 read comparison and causal wording") {
    auto c = told("padeiros_1000", "pt");
    std::string inverted = c.story.paragraphs[1][2].text;
    inverted.replace(inverted.find("acima de"), 8, "abaixo de");
    CHECK(flags(check_sentence(c, 1, 2, inverted), "V6"));

    CHECK(flags(check_sentence(c, 1, 2, "{sewage.radius} dos domicílios do raio adoecem devido à falta de esgoto."), "V7"));
}

TEST_CASE("domain terms that contain 'causa' are not causal claims") {
    auto c = told("padeiros_1000", "pt");
    const auto issues = story::verify(c.story.paragraphs, c.story.plan, c.story.facts, *c.lang);
    CHECK_FALSE(flags(issues, "V7"));
    const auto& last = c.story.paragraphs.back().back().text;
    CHECK(last.find("causa definida") != std::string::npos);
}

TEST_CASE("the numeric-only baseline misses scale errors") {
    auto c = told("padeiros_1000", "pt");
    const auto mutants = story::mutate(c.story.paragraphs, c.story.plan, c.story.facts, *c.lang);
    const auto scale = std::find_if(mutants.begin(), mutants.end(), [](const auto& m) { return m.op == "M3b"; });
    REQUIRE(scale != mutants.end());
    const auto text = story::plain_text(story::render(scale->paragraphs, c.story.facts, *c.lang));
    CHECK(story::numeric_check_passes(text, c.story.facts, *c.lang));
    CHECK_FALSE(story::verify(scale->paragraphs, c.story.plan, c.story.facts, *c.lang).empty());
}
