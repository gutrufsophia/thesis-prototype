#include "story/realiser.hpp"

#include <stdexcept>

#include "story/format.hpp"

namespace story {

namespace {

std::string replace_all(std::string text, const std::string& from, const std::string& to) {
    for (std::size_t at = text.find(from); at != std::string::npos; at = text.find(from, at + to.size())) {
        text.replace(at, from.size(), to);
    }
    return text;
}

// "%" in a template stands for the fact the text is attached to.
std::string bind_fact(const std::string& text, const std::string& fact) {
    return replace_all(replace_all(text, "{%.", "{" + fact + "."), "<pl:%.", "<pl:" + fact + ".");
}

// <pl:fact.field|singular|plural> agrees with the slot's value.
std::string resolve_plurals(std::string text, const std::vector<Fact>& facts) {
    for (std::size_t at = text.find("<pl:"); at != std::string::npos; at = text.find("<pl:", at)) {
        const std::size_t close = text.find('>', at);
        if (close == std::string::npos) throw std::runtime_error("unclosed plural marker");
        const std::string inner = text.substr(at + 4, close - at - 4);
        const std::size_t bar1 = inner.find('|');
        const std::size_t bar2 = inner.find('|', bar1 + 1);
        const std::size_t dot = inner.find('.');
        if (bar1 == std::string::npos || bar2 == std::string::npos || dot == std::string::npos || dot > bar1) {
            throw std::runtime_error("malformed plural marker: " + inner);
        }
        const Fact* fact = find_fact(facts, inner.substr(0, dot));
        const std::string field = inner.substr(dot + 1, bar1 - dot - 1);
        if (!fact || !fact->slots.count(field)) throw std::runtime_error("plural marker on unknown slot: " + inner);
        const bool one = fact->slots.at(field).number == 1;
        const std::string word = one ? inner.substr(bar1 + 1, bar2 - bar1 - 1) : inner.substr(bar2 + 1);
        text.replace(at, close - at + 1, word);
    }
    return text;
}

std::string append_clause(const std::string& sentence, const std::string& clause) {
    std::string base = sentence;
    while (!base.empty() && (base.back() == '.' || base.back() == ' ')) base.pop_back();
    return base + ", " + clause + ".";
}

std::string fact_sentence(const Fact& fact, const Language& lang) {
    const std::string* tmpl = lang.template_for(fact.id, fact.variant);
    if (!tmpl) throw std::runtime_error("no template for " + fact.id + (fact.variant.empty() ? "" : "." + fact.variant));
    std::string text = *tmpl;
    if (text.find("<cmp>") != std::string::npos) {
        if (!fact.tier) throw std::runtime_error("template for " + fact.id + " compares, but the fact has no tier");
        text = replace_all(text, "<cmp>", lang.comparatives.at(to_string(*fact.tier)));
    }
    return bind_fact(text, fact.id);
}

}  // namespace

std::string caveat_statement(const Caveat& caveat, const std::vector<Fact>& facts, const Language& lang) {
    const CaveatText* text = lang.caveat_for(caveat.rule, caveat.variant);
    if (!text) throw std::runtime_error("no text for caveat " + caveat.rule);
    return resolve_plurals(bind_fact(text->text, caveat.fact), facts);
}

std::vector<Paragraph> realise_templates(const Plan& plan, const std::vector<Fact>& facts, const Language& lang) {
    std::vector<Paragraph> paragraphs;
    for (const auto& ids : plan.paragraphs) {
        Paragraph paragraph;
        for (const auto& id : ids) {
            const Fact* fact = find_fact(facts, id);
            if (!fact) throw std::runtime_error("planned fact not found: " + id);
            Sentence main{resolve_plurals(fact_sentence(*fact, lang), facts), {id}, {}};
            Paragraph before, after;
            for (const auto& c : plan.caveats) {
                if (c.fact != id || c.effect == Effect::Suppress) continue;
                const std::string text = caveat_statement(c, facts, lang);
                if (text.empty()) {
                    main.caveats.push_back(c.rule);  // the template itself carries the statement
                } else if (c.effect == Effect::Qualify) {
                    main.text = append_clause(main.text, text);
                    main.caveats.push_back(c.rule);
                } else {
                    (c.before ? before : after).push_back({text, {}, {c.rule}});
                }
            }
            paragraph.insert(paragraph.end(), before.begin(), before.end());
            paragraph.push_back(main);
            paragraph.insert(paragraph.end(), after.begin(), after.end());
        }
        if (!paragraph.empty()) paragraphs.push_back(paragraph);
    }
    return paragraphs;
}

std::vector<Token> tokens(const std::string& text) {
    std::vector<Token> out;
    for (std::size_t open = text.find('{'); open != std::string::npos; open = text.find('{', open + 1)) {
        const std::size_t close = text.find('}', open);
        if (close == std::string::npos) break;
        const std::string inner = text.substr(open + 1, close - open - 1);
        const std::size_t dot = inner.find('.');
        if (dot == std::string::npos) continue;
        out.push_back({open, close + 1, inner.substr(0, dot), inner.substr(dot + 1)});
    }
    return out;
}

std::string format_slot(const Slot& slot, const Language& lang) {
    const auto& style = lang.style;
    switch (slot.kind) {
        case Slot::Kind::Count: return format_number(slot.number, 0, style);
        case Slot::Kind::Estimate: return format_estimate(slot.number, style);
        case Slot::Kind::Percent: return format_number(slot.number, slot.digits, style) + "%";
        case Slot::Kind::Rate:
        case Slot::Kind::Decimal: return format_number(slot.number, slot.digits, style);
        case Slot::Kind::Ratio: return format_ratio(slot.number, style);
        case Slot::Kind::Distance: return format_distance(slot.number, style);
        case Slot::Kind::Year: return std::to_string(static_cast<int>(slot.number));
        case Slot::Kind::Text: return slot.text;
        case Slot::Kind::Label: return lang.label(slot.text);
    }
    return {};
}

nlohmann::json render(const std::vector<Paragraph>& paragraphs, const std::vector<Fact>& facts, const Language& lang) {
    nlohmann::json out = nlohmann::json::array();
    for (const auto& paragraph : paragraphs) {
        nlohmann::json p = nlohmann::json::array();
        for (const auto& sentence : paragraph) {
            nlohmann::json segments = nlohmann::json::array();
            std::size_t cursor = 0;
            for (const auto& t : tokens(sentence.text)) {
                if (t.begin > cursor) segments.push_back({{"text", sentence.text.substr(cursor, t.begin - cursor)}});
                nlohmann::json segment;
                if (t.owner == "k") {
                    segment["text"] = lang.constants.at(t.field);
                } else {
                    const Fact* fact = find_fact(facts, t.owner);
                    if (!fact || !fact->slots.count(t.field)) {
                        throw std::runtime_error("unknown slot " + t.owner + "." + t.field);
                    }
                    segment["text"] = format_slot(fact->slots.at(t.field), lang);
                    segment["fact"] = t.owner;
                    if (auto scope = scope_of_field(t.field)) segment["scope"] = to_string(*scope);
                }
                segments.push_back(segment);
                cursor = t.end;
            }
            if (cursor < sentence.text.size()) segments.push_back({{"text", sentence.text.substr(cursor)}});
            p.push_back({{"segments", segments}, {"facts", sentence.facts}, {"caveats", sentence.caveats}});
        }
        out.push_back(p);
    }
    return out;
}

std::string plain_text(const nlohmann::json& rendered) {
    std::string out;
    for (const auto& paragraph : rendered) {
        if (!out.empty()) out += "\n\n";
        bool first = true;
        for (const auto& sentence : paragraph) {
            if (!first) out += ' ';
            first = false;
            for (const auto& segment : sentence.at("segments")) out += segment.at("text").get<std::string>();
        }
    }
    return out;
}

}  // namespace story
