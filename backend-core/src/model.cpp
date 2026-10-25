#include "story/model.hpp"

#include <algorithm>
#include <array>
#include <utility>

namespace story {

namespace {
const std::array<std::pair<Scope, const char*>, 6> kScopes{{
    {Scope::Unit, "unit"},
    {Scope::Radius, "radius"},
    {Scope::District, "district"},
    {Scope::City, "city"},
    {Scope::Municipality, "municipality"},
    {Scope::Region, "region"},
}};
}  // namespace

std::string to_string(Scope scope) {
    for (const auto& [s, name] : kScopes) {
        if (s == scope) return name;
    }
    return "unit";
}

std::optional<Scope> scope_from_string(const std::string& name) {
    for (const auto& [s, n] : kScopes) {
        if (name == n) return s;
    }
    return std::nullopt;
}

std::optional<Scope> scope_of_field(const std::string& field) {
    if (auto s = scope_from_string(field)) return s;
    const auto cut = field.rfind('_');
    if (cut == std::string::npos) return std::nullopt;
    return scope_from_string(field.substr(cut + 1));
}

std::string to_string(Tier tier) {
    switch (tier) {
        case Tier::Similar: return "similar";
        case Tier::Higher: return "higher";
        case Tier::MuchHigher: return "much_higher";
        case Tier::TimesHigher: return "times_higher";
        case Tier::Lower: return "lower";
        case Tier::MuchLower: return "much_lower";
    }
    return "similar";
}

const Fact* find_fact(const std::vector<Fact>& facts, const std::string& id) {
    auto it = std::find_if(facts.begin(), facts.end(), [&](const Fact& f) { return f.id == id; });
    return it == facts.end() ? nullptr : &*it;
}

Fact* find_fact(std::vector<Fact>& facts, const std::string& id) {
    auto it = std::find_if(facts.begin(), facts.end(), [&](const Fact& f) { return f.id == id; });
    return it == facts.end() ? nullptr : &*it;
}

}  // namespace story
