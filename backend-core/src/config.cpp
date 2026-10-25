#include "story/config.hpp"

#include <fstream>
#include <stdexcept>

namespace story {

namespace {

nlohmann::json read_json(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open " + path);
    return nlohmann::json::parse(in);
}

std::regex pattern(const std::string& source) {
    return std::regex(source, std::regex::icase | std::regex::ECMAScript);
}

Effect effect_from(const std::string& name) {
    if (name == "suppress") return Effect::Suppress;
    if (name == "disclose") return Effect::Disclose;
    if (name == "qualify") return Effect::Qualify;
    throw std::runtime_error("unknown caveat effect: " + name);
}

Language load_language(const std::string& path) {
    const auto j = read_json(path);
    Language lang;
    lang.code = j.at("code");
    lang.style = {j.at("decimal").get<std::string>()[0], j.at("thousands").get<std::string>()[0]};
    lang.templates = j.at("templates").get<std::map<std::string, std::string>>();
    lang.comparatives = j.at("comparatives").get<std::map<std::string, std::string>>();
    lang.labels = j.at("labels").get<std::map<std::string, std::string>>();
    lang.constants = j.at("constants").get<std::map<std::string, std::string>>();
    lang.max_words = j.value("max_words", 220);
    for (const auto& [id, c] : j.at("caveats").items()) {
        const std::string marker = c.at("marker");
        lang.caveats[id] = {c.value("text", ""), pattern(marker), marker};
    }
    for (const auto& [scope, markers] : j.at("scope_markers").items()) {
        const auto s = scope_from_string(scope);
        if (!s) throw std::runtime_error("unknown scope in markers: " + scope);
        for (const auto& m : markers) lang.scope_markers.emplace_back(*s, pattern(m.get<std::string>()));
    }
    for (const auto& [direction, words] : j.at("direction_words").items()) {
        for (const auto& w : words) lang.direction_words[direction].push_back(pattern(w.get<std::string>()));
    }
    for (const auto& c : j.at("causal")) lang.causal.push_back(pattern(c.get<std::string>()));
    lang.protected_terms = j.at("protected_terms").get<std::vector<std::string>>();
    lang.clause_separators = j.at("clause_separators").get<std::vector<std::string>>();
    lang.mutation = j.value("mutation", nlohmann::json::object());
    return lang;
}

}  // namespace

const std::string* Language::template_for(const std::string& fact, const std::string& variant) const {
    if (!variant.empty()) {
        if (auto it = templates.find(fact + "." + variant); it != templates.end()) return &it->second;
    }
    auto it = templates.find(fact);
    return it == templates.end() ? nullptr : &it->second;
}

const CaveatText* Language::caveat_for(const std::string& rule, const std::string& variant) const {
    if (!variant.empty()) {
        if (auto it = caveats.find(rule + "." + variant); it != caveats.end()) return &it->second;
    }
    auto it = caveats.find(rule);
    return it == caveats.end() ? nullptr : &it->second;
}

std::string Language::label(const std::string& key) const {
    auto it = labels.find(key);
    return it == labels.end() ? key : it->second;
}

const Rule& Config::rule(const std::string& id) const {
    for (const auto& r : rules) {
        if (r.id == id) return r;
    }
    throw std::runtime_error("unknown rule: " + id);
}

const Language& Config::language(const std::string& code) const {
    auto it = languages.find(code);
    if (it == languages.end()) throw std::runtime_error("unsupported language: " + code);
    return it->second;
}

Config load_config(const std::string& dir) {
    Config config;
    const auto rules = read_json(dir + "/rules.json");
    config.params = rules.at("params");
    for (const auto& r : rules.at("rules")) {
        config.rules.push_back({r.at("id"), r.value("note", 0), effect_from(r.at("effect")), r.at("fact"),
                                r.value("before", false), r.value("params", nlohmann::json::object())});
    }
    for (const char* code : {"pt", "en"}) {
        config.languages[code] = load_language(dir + "/" + code + ".json");
    }
    return config;
}

}  // namespace story
