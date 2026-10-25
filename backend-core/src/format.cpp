#include "story/format.hpp"

#include <cmath>
#include <string>

namespace story {

std::string format_number(double value, int digits, const NumberStyle& style) {
    const double scale = std::pow(10.0, digits);
    const long long scaled = std::llround(std::fabs(value) * scale);
    const long long whole = scaled / static_cast<long long>(scale);
    const long long fraction = scaled % static_cast<long long>(scale);

    std::string integer = std::to_string(whole);
    std::string grouped;
    for (std::size_t i = 0; i < integer.size(); ++i) {
        if (i > 0 && (integer.size() - i) % 3 == 0) grouped += style.thousands;
        grouped += integer[i];
    }
    std::string out = (value < 0 && scaled != 0) ? "-" + grouped : grouped;
    if (digits > 0) {
        std::string frac = std::to_string(fraction);
        out += style.decimal + std::string(digits - frac.size(), '0') + frac;
    }
    return out;
}

std::string format_estimate(double value, const NumberStyle& style) {
    if (std::fabs(value) < 100) return format_number(value, 0, style);
    const double magnitude = std::pow(10.0, std::floor(std::log10(std::fabs(value))) - 1);
    return format_number(std::round(value / magnitude) * magnitude, 0, style);
}

std::string format_ratio(double value, const NumberStyle& style) {
    const double half = std::round(value * 2) / 2;
    return format_number(half, half == std::floor(half) ? 0 : 1, style);
}

std::string format_distance(double metres, const NumberStyle& style) {
    if (metres < 1000) return format_number(std::round(metres), 0, style) + " m";
    return format_number(metres / 1000, 1, style) + " km";
}

}  // namespace story
