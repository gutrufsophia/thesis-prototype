#pragma once

#include <map>
#include <optional>
#include <string>
#include <vector>

namespace story {

// The spatial scale a figure describes. Every value slot is bound to one.
enum class Scope { Unit, Radius, District, City, Municipality, Region };

std::string to_string(Scope scope);
std::optional<Scope> scope_from_string(const std::string& name);

// A slot field named after a scope ("radius") or ending in "_<scope>" ("count_municipality")
// carries a value at that scale; any other field ("ratio", "period") has none.
std::optional<Scope> scope_of_field(const std::string& field);

struct Slot {
    enum class Kind { Count, Estimate, Percent, Rate, Decimal, Ratio, Distance, Year, Text, Label };
    Kind kind = Kind::Text;
    double number = 0;
    int digits = 0;
    std::string text;  // Text: shown as is; Label: key into the language's labels

    static Slot count(double n) { return {Kind::Count, n, 0, {}}; }
    static Slot estimate(double n) { return {Kind::Estimate, n, 0, {}}; }
    static Slot percent(double n) { return {Kind::Percent, n, 1, {}}; }
    static Slot rate(double n, int digits) { return {Kind::Rate, n, digits, {}}; }
    static Slot decimal(double n, int digits) { return {Kind::Decimal, n, digits, {}}; }
    static Slot ratio(double n) { return {Kind::Ratio, n, 1, {}}; }
    static Slot distance(double metres) { return {Kind::Distance, metres, 0, {}}; }
    static Slot year(int y) { return {Kind::Year, static_cast<double>(y), 0, {}}; }
    static Slot text_value(std::string s) { return {Kind::Text, 0, 0, std::move(s)}; }
    static Slot label(std::string key) { return {Kind::Label, 0, 0, std::move(key)}; }
};

// Lexical tier of a comparison between a local value and its reference.
enum class Tier { Similar, Higher, MuchHigher, TimesHigher, Lower, MuchLower };

std::string to_string(Tier tier);

struct Fact {
    std::string id;
    std::string kind;   // profile, value, contrast, rank, composition, quality
    std::string theme;  // unit, living, access, network, outcome
    std::map<std::string, Slot> slots;
    std::string variant;  // selects a template variant, e.g. "small" or "hospital"
    std::optional<Tier> tier;
    double salience = 0;
    double weight = 1;
    double reliability = 1;
    bool mandatory = false;
    std::vector<std::string> pairs_with;  // outcome facts: living facts they relate to

    double importance() const { return salience * weight * reliability; }
};

enum class Effect { Suppress, Qualify, Disclose };

struct Caveat {
    std::string rule;
    Effect effect = Effect::Qualify;
    std::string fact;
    std::string variant;
    bool before = false;  // Disclose only: placed before the fact's sentence
};

struct Sentence {
    std::string text;  // with {fact.field} and {k.constant} tokens
    std::vector<std::string> facts;
    std::vector<std::string> caveats;
};

using Paragraph = std::vector<Sentence>;

struct Plan {
    std::vector<std::vector<std::string>> paragraphs;  // fact ids, in order
    std::vector<Caveat> caveats;                        // only those attached to planned facts
};

const Fact* find_fact(const std::vector<Fact>& facts, const std::string& id);
Fact* find_fact(std::vector<Fact>& facts, const std::string& id);

}  // namespace story
