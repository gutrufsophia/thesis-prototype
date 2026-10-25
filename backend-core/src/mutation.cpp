#include "story/mutation.hpp"

#include <algorithm>
#include <map>
#include <regex>
#include <set>

#include "story/realiser.hpp"

namespace story {

namespace {

bool is_value(const Slot& slot) { return slot.kind != Slot::Kind::Text && slot.kind != Slot::Kind::Label; }

const Slot* slot_of(const std::vector<Fact>& facts, const Token& t) {
    if (t.owner == "k") return nullptr;
    const Fact* f = find_fact(facts, t.owner);
    if (!f || !f->slots.count(t.field)) return nullptr;
    return &f->slots.at(t.field);
}

std::string blank(const std::string& text) {
    std::string out = text;
    for (const auto& t : tokens(text)) std::fill(out.begin() + t.begin, out.begin() + t.end, ' ');
    return out;
}

std::string with_clause(const std::string& sentence, const std::string& clause) {
    std::string base = sentence;
    while (!base.empty() && (base.back() == '.' || base.back() == ' ')) base.pop_back();
    return base + ", " + clause + ".";
}

Scope swapped(Scope s) {
    switch (s) {
        case Scope::Radius: return Scope::Municipality;
        case Scope::Municipality: return Scope::Radius;
        case Scope::District: return Scope::Municipality;
        case Scope::City: return Scope::Region;
        case Scope::Region: return Scope::Municipality;
        case Scope::Unit: return Scope::Radius;
    }
    return Scope::Radius;
}

}  // namespace

std::vector<Mutant> mutate(const std::vector<Paragraph>& paragraphs, const Plan& plan, const std::vector<Fact>& facts,
                           const Language& lang) {
    std::set<std::string> planned;
    for (const auto& p : plan.paragraphs) planned.insert(p.begin(), p.end());
    std::vector<Mutant> out;

    auto emit = [&](const char* op, std::string detail, int pi, int si, std::string text) {
        auto copy = paragraphs;
        copy[pi][si].text = std::move(text);
        out.push_back({op, std::move(detail), std::move(copy)});
    };

    for (int pi = 0; pi < static_cast<int>(paragraphs.size()); ++pi) {
        for (int si = 0; si < static_cast<int>(paragraphs[pi].size()); ++si) {
            const std::string& text = paragraphs[pi][si].text;
            const auto toks = tokens(text);
            const std::string blanked = blank(text);

            const Token* value = nullptr;
            for (const auto& t : toks) {
                const Slot* s = slot_of(facts, t);
                if (s && is_value(*s)) {
                    value = &t;
                    break;
                }
            }

            if (value) {
                const Slot& slot = *slot_of(facts, *value);
                const std::string name = value->owner + "." + value->field;
                std::string literal = text;
                literal.replace(value->begin, value->end - value->begin, format_slot(slot, lang));
                emit("M1", name, pi, si, literal);

                Slot wrong = slot;
                wrong.number = slot.number * 1.37 + 1;
                std::string altered = text;
                altered.replace(value->begin, value->end - value->begin, format_slot(wrong, lang));
                emit("M1b", name, pi, si, altered);

                if (const auto scope = scope_of_field(value->field)) {
                    for (const auto& f : facts) {
                        if (planned.count(f.id)) continue;
                        const auto other = std::find_if(f.slots.begin(), f.slots.end(), [&](const auto& s) {
                            return is_value(s.second) && scope_of_field(s.first) == scope;
                        });
                        if (other == f.slots.end()) continue;
                        std::string foreign = text;
                        foreign.replace(value->begin, value->end - value->begin, "{" + f.id + "." + other->first + "}");
                        emit("M2", name + " -> " + f.id + "." + other->first, pi, si, foreign);
                        break;
                    }
                }

                emit("M6", name, pi, si, with_clause(text, lang.mutation.at("causal_clause").get<std::string>()));
            }

            for (const auto& [scope, re] : lang.scope_markers) {
                std::smatch m;
                if (!std::regex_search(blanked, m, re)) continue;
                const std::string target = lang.mutation.at("scope_words").at(to_string(swapped(scope)));
                std::string changed = text;
                changed.replace(static_cast<std::size_t>(m.position()), static_cast<std::size_t>(m.length()), target);
                emit("M3", to_string(scope) + " -> " + to_string(swapped(scope)), pi, si, changed);
                break;
            }

            for (std::size_t a = 0; a < toks.size(); ++a) {
                bool done = false;
                for (std::size_t b = a + 1; b < toks.size() && !done; ++b) {
                    const Slot* sa = slot_of(facts, toks[a]);
                    const Slot* sb = slot_of(facts, toks[b]);
                    const auto ca = scope_of_field(toks[a].field);
                    const auto cb = scope_of_field(toks[b].field);
                    if (!sa || !sb || !is_value(*sa) || !is_value(*sb) || !ca || !cb || *ca == *cb) continue;
                    if (toks[a].owner != toks[b].owner || *ca == Scope::Unit || *cb == Scope::Unit) continue;
                    std::string swapped_text = text;
                    const std::string ta = text.substr(toks[a].begin, toks[a].end - toks[a].begin);
                    const std::string tb = text.substr(toks[b].begin, toks[b].end - toks[b].begin);
                    swapped_text.replace(toks[b].begin, toks[b].end - toks[b].begin, ta);
                    swapped_text.replace(toks[a].begin, toks[a].end - toks[a].begin, tb);
                    emit("M3b", toks[a].field + " <-> " + toks[b].field, pi, si, swapped_text);
                    done = true;
                }
                if (done) break;
            }

            std::vector<std::pair<std::string, std::string>> opposites;
            for (const auto& [from, to] : lang.mutation.at("opposites").items()) {
                opposites.emplace_back(from, to.get<std::string>());
            }
            std::sort(opposites.begin(), opposites.end(),
                      [](const auto& x, const auto& y) { return x.first.size() > y.first.size(); });
            const bool compares = std::any_of(toks.begin(), toks.end(), [&](const Token& t) {
                const Fact* f = t.owner == "k" ? nullptr : find_fact(facts, t.owner);
                return f && f->tier;
            });
            for (const auto& [from, to] : opposites) {
                if (!compares) break;
                const std::size_t at = blanked.find(from);
                if (at == std::string::npos) continue;
                std::string inverted = text;
                inverted.replace(at, from.size(), to);
                emit("M4", from + " -> " + to, pi, si, inverted);
                break;
            }

            for (const auto& t : toks) {
                if (t.field != "period" && t.field != "year") continue;
                const Slot* own = slot_of(facts, t);
                if (!own) continue;
                const std::string own_text = format_slot(*own, lang);
                const Fact* donor = nullptr;
                for (const auto& f : facts) {
                    if (f.id == t.owner || !f.slots.count(t.field)) continue;
                    if (format_slot(f.slots.at(t.field), lang) == own_text) continue;
                    if (!donor || (planned.count(f.id) && !planned.count(donor->id))) donor = &f;
                }
                if (!donor) continue;
                std::string changed = text;
                changed.replace(t.begin, t.end - t.begin, "{" + donor->id + "." + t.field + "}");
                emit("M7", t.owner + "." + t.field + " -> " + donor->id, pi, si, changed);
                break;
            }
        }
    }

    for (const auto& c : plan.caveats) {
        if (c.effect == Effect::Suppress) continue;
        const CaveatText* caveat = lang.caveat_for(c.rule, c.variant);
        if (!caveat) continue;
        bool removed = false;
        for (int pi = 0; pi < static_cast<int>(paragraphs.size()) && !removed; ++pi) {
            for (int si = 0; si < static_cast<int>(paragraphs[pi].size()) && !removed; ++si) {
                const auto& s = paragraphs[pi][si];
                if (std::find(s.caveats.begin(), s.caveats.end(), c.rule) == s.caveats.end()) continue;
                auto copy = paragraphs;
                if (s.facts.empty()) {
                    copy[pi].erase(copy[pi].begin() + si);
                } else {
                    copy[pi][si].text = std::regex_replace(s.text, caveat->marker, "");
                }
                out.push_back({"M5", c.rule, std::move(copy)});
                removed = true;
            }
        }
    }
    return out;
}

bool numeric_check_passes(const std::string& rendered, const std::vector<Fact>& facts, const Language& lang) {
    const std::regex number(R"(\d+(?:[.,]\d+)*)");
    std::set<std::string> known;
    auto collect = [&](const std::string& s) {
        for (auto it = std::sregex_iterator(s.begin(), s.end(), number); it != std::sregex_iterator(); ++it) {
            known.insert(it->str());
        }
    };
    for (const auto& f : facts) {
        for (const auto& [_, slot] : f.slots) collect(format_slot(slot, lang));
    }
    for (const auto& [_, value] : lang.constants) collect(value);
    for (const auto& [_, value] : lang.labels) collect(value);
    for (auto it = std::sregex_iterator(rendered.begin(), rendered.end(), number); it != std::sregex_iterator(); ++it) {
        std::string n = it->str();
        while (!n.empty() && (n.back() == '.' || n.back() == ',')) n.pop_back();
        if (!known.count(n)) return false;
    }
    return true;
}

}  // namespace story
