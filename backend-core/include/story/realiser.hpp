#pragma once

#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "story/config.hpp"
#include "story/model.hpp"

namespace story {

// Turns the plan into sentences that still carry {fact.field} and {k.constant} tokens.
// Numbers never pass through the realiser: they are only inserted by render().
std::vector<Paragraph> realise_templates(const Plan& plan, const std::vector<Fact>& facts, const Language& lang);

// The resolved text of a caveat for the fact it is attached to; empty when the template carries it.
std::string caveat_statement(const Caveat& caveat, const std::vector<Fact>& facts, const Language& lang);

struct Token {
    std::size_t begin = 0;
    std::size_t end = 0;  // one past the closing brace
    std::string owner;    // fact id, or "k" for a constant
    std::string field;
};

std::vector<Token> tokens(const std::string& text);

std::string format_slot(const Slot& slot, const Language& lang);

// Replaces every token by its formatted value. Each sentence becomes a list of segments,
// and a segment that came from a slot carries the slot's scale and fact.
nlohmann::json render(const std::vector<Paragraph>& paragraphs, const std::vector<Fact>& facts, const Language& lang);

std::string plain_text(const nlohmann::json& rendered);

}  // namespace story
