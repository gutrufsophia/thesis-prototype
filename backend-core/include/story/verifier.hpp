#pragma once

#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "story/config.hpp"
#include "story/model.hpp"

namespace story {

struct Issue {
    std::string check;  // V1 ... V8
    int paragraph = -1;
    int sentence = -1;
    std::string detail;
};

// Checks a realisation, still carrying its tokens, against the plan and the facts. It trusts
// nothing the realiser reports about itself: facts and caveats are located by their tokens.
//   V1 no number outside a slot          V5 each value's nearest scale marker in its clause is its
//                                           own (or, in a single-scale sentence, the sentence's)
//   V2 every slot exists in the plan     V6 comparison words agree with the data
//   V3 every planned fact is told        V7 no causal wording
//   V4 every caveat's statement is there V8 length limit
std::vector<Issue> verify(const std::vector<Paragraph>& paragraphs, const Plan& plan, const std::vector<Fact>& facts,
                          const Language& lang);

// Words in the realisation, counting each token as one word (V8 uses the same count).
std::size_t word_count(const std::vector<Paragraph>& paragraphs);

nlohmann::json to_json(const std::vector<Issue>& issues);

}  // namespace story
