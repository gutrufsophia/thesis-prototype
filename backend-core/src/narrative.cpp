#include "story/narrative.hpp"

#include <algorithm>
#include <set>

#include "story/caveats.hpp"
#include "story/facts.hpp"
#include "story/planner.hpp"
#include "story/realiser.hpp"
#include "story/verifier.hpp"

namespace story {

namespace {

std::string effect_name(Effect e) {
    switch (e) {
        case Effect::Suppress: return "suppress";
        case Effect::Qualify: return "qualify";
        case Effect::Disclose: return "disclose";
    }
    return "qualify";
}

bool is_planned(const Plan& plan, const std::string& id) {
    for (const auto& p : plan.paragraphs) {
        if (std::find(p.begin(), p.end(), id) != p.end()) return true;
    }
    return false;
}

// Candidates are facts the schema does not require; the last outcome is always kept.
std::string least_important_optional(const Plan& plan, const std::vector<Fact>& facts) {
    std::string drop;
    double lowest = 0;
    for (std::size_t pi = 0; pi < plan.paragraphs.size(); ++pi) {
        for (const auto& id : plan.paragraphs[pi]) {
            const Fact* f = find_fact(facts, id);
            if (!f || f->mandatory || (pi == 2 && plan.paragraphs[pi].size() == 1)) continue;
            if (drop.empty() || f->importance() < lowest) {
                drop = id;
                lowest = f->importance();
            }
        }
    }
    return drop;
}

void remove_from_plan(Plan& plan, const std::string& id) {
    for (auto& p : plan.paragraphs) p.erase(std::remove(p.begin(), p.end(), id), p.end());
}

nlohmann::json fact_json(const Fact& f, const Language& lang) {
    nlohmann::json slots = nlohmann::json::object();
    for (const auto& [field, slot] : f.slots) {
        nlohmann::json s{{"text", format_slot(slot, lang)}};
        if (slot.kind != Slot::Kind::Text && slot.kind != Slot::Kind::Label) s["value"] = slot.number;
        if (auto scope = scope_of_field(field)) s["scope"] = to_string(*scope);
        slots[field] = s;
    }
    nlohmann::json j{{"id", f.id},           {"kind", f.kind},
                     {"theme", f.theme},     {"variant", f.variant},
                     {"salience", f.salience}, {"weight", f.weight},
                     {"reliability", f.reliability}, {"importance", f.importance()},
                     {"slots", slots}};
    if (f.tier) j["tier"] = to_string(*f.tier);
    return j;
}

}  // namespace

Story tell(const Payload& payload, const Config& config, const std::string& code) {
    const Language& lang = config.language(code);
    Story story;
    auto& facts = story.facts;
    auto& plan = story.plan;
    facts = extract_facts(payload, config.params);
    const auto pre = apply_pre_rules(payload, config, facts);
    plan = plan_document(facts, config.params);
    for (const auto& c : pre) {
        if (c.effect == Effect::Suppress) story.suppressed.push_back(c);
    }

    auto attach_caveats = [&] {
        plan.caveats = apply_post_rules(payload, config, facts, plan);
        for (const auto& c : pre) {
            if (c.effect != Effect::Suppress && is_planned(plan, c.fact)) plan.caveats.push_back(c);
        }
    };
    // Length budget: drop the least important optional fact until the text fits in every
    // language, so Portuguese and English always tell the same facts.
    auto& trimmed = story.trimmed;
    for (;;) {
        attach_caveats();
        bool fits = true;
        for (const auto& [_, l] : config.languages) {
            if (word_count(realise_templates(plan, facts, l)) > static_cast<std::size_t>(l.max_words)) fits = false;
        }
        if (fits) break;
        const auto drop = least_important_optional(plan, facts);
        if (drop.empty()) break;
        remove_from_plan(plan, drop);
        trimmed.push_back(drop);
    }

    story.paragraphs = realise_templates(plan, facts, lang);
    return story;
}

nlohmann::json narrate(const Payload& payload, const Config& config, const std::string& code) {
    const Language& lang = config.language(code);
    const Story story = tell(payload, config, code);
    const auto& facts = story.facts;
    const auto& plan = story.plan;
    const auto& paragraphs = story.paragraphs;
    std::set<std::string> planned;
    for (const auto& p : plan.paragraphs) planned.insert(p.begin(), p.end());

    const auto issues = verify(paragraphs, plan, facts, lang);
    const auto rendered = render(paragraphs, facts, lang);

    nlohmann::json caveats = nlohmann::json::array();
    auto add_caveat = [&](const Caveat& c) {
        caveats.push_back({{"rule", c.rule},
                           {"note", config.rule(c.rule).note},
                           {"effect", effect_name(c.effect)},
                           {"fact", c.fact},
                           {"variant", c.variant}});
    };
    for (const auto& c : plan.caveats) add_caveat(c);
    for (const auto& c : story.suppressed) add_caveat(c);

    nlohmann::json fact_list = nlohmann::json::array();
    for (const auto& f : facts) {
        auto j = fact_json(f, lang);
        j["planned"] = planned.count(f.id) > 0;
        fact_list.push_back(j);
    }

    nlohmann::json slotted = nlohmann::json::array();
    for (const auto& p : paragraphs) {
        nlohmann::json sentences = nlohmann::json::array();
        for (const auto& s : p) sentences.push_back(s.text);
        slotted.push_back(sentences);
    }

    return {{"version", kVersion},
            {"lang", code},
            {"realiser", "template"},
            {"verified", issues.empty()},
            {"issues", to_json(issues)},
            {"paragraphs", rendered},
            {"text", plain_text(rendered)},
            {"slotted", slotted},
            {"plan", plan.paragraphs},
            {"trimmed_for_length", story.trimmed},
            {"facts", fact_list},
            {"caveats", caveats}};
}

}  // namespace story
