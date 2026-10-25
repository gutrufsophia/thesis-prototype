#include <catch2/catch_test_macros.hpp>

#include "story/format.hpp"

using story::NumberStyle;

namespace {
const NumberStyle pt{',', '.'};
const NumberStyle en{'.', ','};
}  // namespace

TEST_CASE("numbers follow the frontend's locale formatting") {
    CHECK(story::format_number(1543, 0, pt) == "1.543");
    CHECK(story::format_number(1543, 0, en) == "1,543");
    CHECK(story::format_number(90.6, 1, pt) == "90,6");
    CHECK(story::format_number(1234567.891, 2, en) == "1,234,567.89");
    CHECK(story::format_number(0.04, 1, pt) == "0,0");
    CHECK(story::format_number(5.0, 1, pt) == "5,0");
    CHECK(story::format_number(-2.25, 1, en) == "-2.3");
}

TEST_CASE("estimates keep two significant figures") {
    CHECK(story::format_estimate(63, pt) == "63");
    CHECK(story::format_estimate(169, pt) == "170");
    CHECK(story::format_estimate(1354, pt) == "1.400");
    CHECK(story::format_estimate(51715, en) == "52,000");
}

TEST_CASE("ratios are rounded to the nearest half") {
    CHECK(story::format_ratio(3.1, pt) == "3");
    CHECK(story::format_ratio(2.3, pt) == "2,5");
    CHECK(story::format_ratio(2.74, en) == "2.5");
}

TEST_CASE("distances follow the frontend's formatDistance") {
    CHECK(story::format_distance(500, pt) == "500 m");
    CHECK(story::format_distance(1000, pt) == "1,0 km");
    CHECK(story::format_distance(5278, en) == "5.3 km");
}
