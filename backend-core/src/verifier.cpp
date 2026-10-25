#include "story/verifier.hpp"

#include <algorithm>
#include <cctype>
#include <map>
#include <regex>
#include <set>

#include "story/realiser.hpp"

namespace story {

namespace {

struct Marker {
    std::size_t begin;
    std::size_t end;
    Scope scope;
};

struct Range {
    std::size_t begin;
    std::size_t end;
};

// The sentence with every token blanked out, so positions are kept and words inside tokens
// ("municipality", digits in names) are never read as part of the prose.
std::string blank_tokens(const std::string& text, const std::vector<Token>& toks) {
    std::string out = text;
    for (const auto& t : toks) std::fill(out.begin() + t.begin, out.begin() + t.end, ' ');
    return out;
}

std::string lower_ascii(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
    return s;
}

std::vector<Range> clauses(const std::string& blanked, const std::vector<std::string>& separators) {
    const std::string lowered = lower_ascii(blanked);
    std::vector<std::size_t> cuts{0};
    for (const auto& sep : separators) {
        const std::string s = lower_ascii(sep);
        for (std::size_t at = lowered.find(s); at != std::string::npos; at = lowered.find(s, at + 1)) cuts.push_back(at);
    }
    cuts.push_back(blanked.size());
    std::sort(cuts.begin(), cuts.end());
    std::vector<Range> out;
    for (std::size_t i = 0; i + 1 < cuts.size(); ++i) {
        if (cuts[i + 1] > cuts[i]) out.push_back({cuts[i], cuts[i + 1]});
    }
    return out;
}

std::size_t gap(std::size_t a_begin, std::size_t a_end, std::size_t b_begin, std::size_t b_end) {
    if (b_begin >= a_end) return b_begin - a_end;
    if (a_begin >= b_end) return a_begin - b_end;
    return 0;
}

bool is_value(const Slot& slot) { return slot.kind != Slot::Kind::Text && slot.kind != Slot::Kind::Label; }

const std::map<Tier, std::set<std::string>>& allowed_directions() {
    static const std::map<Tier, std::set<std::string>> allowed{
        {Tier::Similar, {"similar"}},       {Tier::Higher, {"higher"}},   {Tier::MuchHigher, {"higher"}},
        {Tier::TimesHigher, {"times", "higher"}}, {Tier::Lower, {"lower"}}, {Tier::MuchLower, {"lower"}},
    };
    return allowed;
}

std::string mask_protected(std::string text, const std::vector<std::string>& terms) {
    for (const auto& term : terms) {
        std::regex re(std::regex_replace(term, std::regex(R"([.^$|()\[\]{}*+?\\])"), R"(\$&)"), std::regex::icase);
        text = std::regex_replace(text, re, std::string(term.size(), ' '));
    }
    return text;
}

}  // namespace

std::vector<Issue> verify(const std::vector<Paragraph>& paragraphs, const Plan& plan, const std::vector<Fact>& facts,
                          const Language& lang) {
    std::vector<Issue> issues;
    std::set<std::string> planned;
    for (const auto& p : plan.paragraphs) planned.insert(p.begin(), p.end());

    // Where each fact's tokens appear: (paragraph, sentence) pairs.
    std::map<std::string, std::vector<std::pair<int, int>>> seen;
    const std::regex digit("[0-9]");

    for (int pi = 0; pi < static_cast<int>(paragraphs.size()); ++pi) {
        for (int si = 0; si < static_cast<int>(paragraphs[pi].size()); ++si) {
            const std::string& text = paragraphs[pi][si].text;
            const auto toks = tokens(text);
            const std::string blanked = blank_tokens(text, toks);
            auto issue = [&](const char* check, std::string detail) {
                issues.push_back({check, pi, si, std::move(detail)});
            };


            if (std::regex_search(blanked, digit)) issue("V1", "number written outside a slot");

            std::vector<Marker> markers;
            std::map<std::string, std::optional<Tier>> contrasted;
            for (const auto& t : toks) {
                if (t.owner == "k") {
                    if (!lang.constants.count(t.field)) issue("V2", "unknown constant " + t.field);
                    continue;
                }
                const Fact* fact = find_fact(facts, t.owner);
                if (!planned.count(t.owner) || !fact || !fact->slots.count(t.field)) {
                    issue("V2", "slot outside the plan: " + t.owner + "." + t.field);
                    continue;
                }
                seen[t.owner].emplace_back(pi, si);
                if (fact->tier) contrasted[t.owner] = fact->tier;
                const auto scope = scope_of_field(t.field);
                if (scope && !is_value(fact->slots.at(t.field))) markers.push_back({t.begin, t.end, *scope});
            }
            for (const auto& [scope, re] : lang.scope_markers) {
                for (auto it = std::sregex_iterator(blanked.begin(), blanked.end(), re); it != std::sregex_iterator(); ++it) {
                    const auto begin = static_cast<std::size_t>(it->position());
                    markers.push_back({begin, begin + static_cast<std::size_t>(it->length()), scope});
                }
            }

            // A name or period describes a value: it must sit in a sentence that tells a value of
            // the same fact (facts with no values at all, like the unit's profile, are exempt).
            std::set<std::string> with_value;
            for (const auto& t : toks) {
                const Fact* fact = t.owner == "k" ? nullptr : find_fact(facts, t.owner);
                if (fact && fact->slots.count(t.field) && is_value(fact->slots.at(t.field))) with_value.insert(t.owner);
            }
            for (const auto& t : toks) {
                const Fact* fact = t.owner == "k" ? nullptr : find_fact(facts, t.owner);
                if (!fact || !fact->slots.count(t.field) || is_value(fact->slots.at(t.field))) continue;
                const bool has_values = std::any_of(fact->slots.begin(), fact->slots.end(),
                                                    [](const auto& s) { return is_value(s.second); });
                if (has_values && !with_value.count(t.owner)) {
                    issue("V2", t.owner + "." + t.field + " appears without a value of " + t.owner);
                }
            }

            const auto ranges = clauses(blanked, lang.clause_separators);

            // A place name must not follow another scale's word ("o raio de Juquitiba").
            const std::size_t name_window = 12;
            for (const auto& name : markers) {
                const bool is_token = std::any_of(toks.begin(), toks.end(), [&](const Token& t) { return t.begin == name.begin; });
                if (!is_token) continue;
                for (const auto& word : markers) {
                    if (word.end > name.begin || name.begin - word.end > name_window) continue;
                    const bool word_is_token = std::any_of(toks.begin(), toks.end(), [&](const Token& t) { return t.begin == word.begin; });
                    if (!word_is_token && word.scope != name.scope) {
                        issue("V5", "a " + to_string(name.scope) + " name is introduced as " + to_string(word.scope));
                    }
                }
            }

            for (const auto& t : toks) {
                if (t.owner == "k" || !planned.count(t.owner)) continue;
                const Fact* fact = find_fact(facts, t.owner);
                if (!fact || !fact->slots.count(t.field) || !is_value(fact->slots.at(t.field))) continue;
                const auto scope = scope_of_field(t.field);
                if (!scope || *scope == Scope::Unit) continue;
                const auto clause = std::find_if(ranges.begin(), ranges.end(),
                                                 [&](const Range& r) { return t.begin >= r.begin && t.begin < r.end; });
                std::size_t best = std::string::npos;
                std::set<Scope> nearest;
                for (const auto& m : markers) {
                    if (clause == ranges.end() || m.begin < clause->begin || m.begin >= clause->end) continue;
                    const auto g = gap(t.begin, t.end, m.begin, m.end);
                    if (g < best) {
                        best = g;
                        nearest = {m.scope};
                    } else if (g == best) {
                        nearest.insert(m.scope);
                    }
                }
                // A clause without a marker borrows the sentence's, but only when the whole
                // sentence speaks of a single scale; otherwise the attribution is ambiguous.
                if (nearest.empty()) {
                    std::set<Scope> sentence_scopes;
                    for (const auto& m : markers) sentence_scopes.insert(m.scope);
                    if (sentence_scopes.size() == 1) nearest = sentence_scopes;
                }
                const std::string slot = t.owner + "." + t.field;
                if (nearest.empty()) {
                    issue("V5", slot + " has no scale marker in its clause");
                } else if (!nearest.count(*scope)) {
                    issue("V5", slot + " is attributed to the " + to_string(*nearest.begin()) + " scale");
                }
            }

            if (contrasted.size() == 1 && contrasted.begin()->second) {
                const auto& allowed = allowed_directions().at(*contrasted.begin()->second);
                for (const auto& [direction, patterns] : lang.direction_words) {
                    if (allowed.count(direction)) continue;
                    for (const auto& re : patterns) {
                        if (std::regex_search(blanked, re)) {
                            issue("V6", "\"" + direction + "\" wording contradicts " + contrasted.begin()->first);
                        }
                    }
                }
            }

            const std::string masked = mask_protected(blanked, lang.protected_terms);
            for (const auto& re : lang.causal) {
                if (std::regex_search(masked, re)) issue("V7", "causal wording");
            }
        }
    }

    for (int pi = 0; pi < static_cast<int>(plan.paragraphs.size()); ++pi) {
        for (const auto& id : plan.paragraphs[pi]) {
            if (!seen.count(id)) issues.push_back({"V3", pi, -1, "planned fact not told: " + id});
        }
    }

    std::vector<std::string> disclosures;
    for (const auto& c : plan.caveats) {
        if (c.effect != Effect::Disclose) continue;
        const std::string s = caveat_statement(c, facts, lang);
        if (!s.empty()) disclosures.push_back(s);
    }
    auto is_disclosure = [&](const std::string& text) {
        return std::any_of(disclosures.begin(), disclosures.end(),
                           [&](const std::string& d) { return text.find(d) != std::string::npos; });
    };

    for (const auto& c : plan.caveats) {
        if (c.effect == Effect::Suppress || !seen.count(c.fact)) continue;
        const CaveatText* text = lang.caveat_for(c.rule, c.variant);
        if (!text) continue;
        bool found = false;
        // A disclosure is fixed wording, like a disclaimer: it must appear exactly as written.
        const std::string statement = c.effect == Effect::Disclose ? caveat_statement(c, facts, lang) : "";
        for (const auto& [pi, si] : seen.at(c.fact)) {
            if (!statement.empty()) {
                for (const auto& s : paragraphs[pi]) found = found || s.text.find(statement) != std::string::npos;
            } else if (c.effect == Effect::Qualify) {
                // A qualifier belongs to the sentence it qualifies, not to a disclosure about the same fact.
                if (is_disclosure(paragraphs[pi][si].text)) continue;
                const auto& s = paragraphs[pi][si].text;
                found = found || std::regex_search(blank_tokens(s, tokens(s)), text->marker);
            } else {
                for (const auto& s : paragraphs[pi]) {
                    found = found || std::regex_search(blank_tokens(s.text, tokens(s.text)), text->marker);
                }
            }
        }
        if (!found) issues.push_back({"V4", seen.at(c.fact).front().first, -1, "caveat " + c.rule + " is missing"});
    }

    const std::size_t words = word_count(paragraphs);
    if (words > static_cast<std::size_t>(lang.max_words)) {
        issues.push_back({"V8", -1, -1, std::to_string(words) + " words"});
    }
    return issues;
}

std::size_t word_count(const std::vector<Paragraph>& paragraphs) {
    std::size_t words = 0;
    for (const auto& paragraph : paragraphs) {
        for (const auto& sentence : paragraph) {
            const auto toks = tokens(sentence.text);
            bool in_word = false;
            for (char c : blank_tokens(sentence.text, toks)) {
                const bool space = std::isspace(static_cast<unsigned char>(c));
                if (!space && !in_word) ++words;
                in_word = !space;
            }
            words += toks.size();
        }
    }
    return words;
}

nlohmann::json to_json(const std::vector<Issue>& issues) {
    nlohmann::json out = nlohmann::json::array();
    for (const auto& i : issues) {
        out.push_back({{"check", i.check}, {"paragraph", i.paragraph}, {"sentence", i.sentence}, {"detail", i.detail}});
    }
    return out;
}

}  // namespace story
