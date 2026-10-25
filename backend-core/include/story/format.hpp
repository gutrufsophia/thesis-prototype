#pragma once

#include <string>

namespace story {

struct NumberStyle {
    char decimal = ',';
    char thousands = '.';
};

// Same output as the frontend's formatNumber (toLocaleString with fixed digits).
std::string format_number(double value, int digits, const NumberStyle& style);

// Estimates are rounded to two significant figures, so they do not read as counts.
std::string format_estimate(double value, const NumberStyle& style);

// Ratios are rounded to the nearest half: 2.3 -> "2,5", 3.1 -> "3".
std::string format_ratio(double value, const NumberStyle& style);

// Same output as the frontend's formatDistance.
std::string format_distance(double metres, const NumberStyle& style);

}  // namespace story
