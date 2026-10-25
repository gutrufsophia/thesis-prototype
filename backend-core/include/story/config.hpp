#pragma once

#include <map>
#include <regex>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "story/format.hpp"
#include "story/model.hpp"

namespace story {

struct CaveatText {
    std::string text;  // clause (Qualify) or sentence (Disclose); empty when the template carries it
    std::regex marker;
    std::string marker_source;
};

struct Language {
    std::string code;
    NumberStyle style;
    std::map<std::string, std::string> templates;    // "fact" or "fact.variant"
    std::map<std::string, std::string> comparatives;  // by tier name
    std::map<std::string, std::string> labels;
    std::map<std::string, std::string> constants;
    std::map<std::string, CaveatText> caveats;        // "rule" or "rule.variant"
    std::vector<std::pair<Scope, std::regex>> scope_markers;
    std::map<std::string, std::vector<std::regex>> direction_words;  // higher, lower, similar, times
    std::vector<std::regex> causal;
    std::vector<std::string> protected_terms;
    std::vector<std::string> clause_separators;
    nlohmann::json mutation;  // lexicon for the fault-injection evaluation only
    int max_words = 220;

    const std::string* template_for(const std::string& fact, const std::string& variant) const;
    const CaveatText* caveat_for(const std::string& rule, const std::string& variant) const;
    std::string label(const std::string& key) const;
};

struct Rule {
    std::string id;
    int note = 0;
    Effect effect = Effect::Qualify;
    std::string fact;
    bool before = false;
    nlohmann::json params;
};

struct Config {
    std::vector<Rule> rules;
    nlohmann::json params;
    std::map<std::string, Language> languages;

    const Rule& rule(const std::string& id) const;
    const Language& language(const std::string& code) const;
};

Config load_config(const std::string& dir);

}  // namespace story
