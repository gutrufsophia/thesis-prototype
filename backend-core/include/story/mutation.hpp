#pragma once

#include <string>
#include <vector>

#include "story/config.hpp"
#include "story/model.hpp"

namespace story {

struct Mutant {
    std::string op;
    std::string detail;
    std::vector<Paragraph> paragraphs;
};

// Fault injection for evaluating the verifier (mutation analysis). Each operator plants one
// error of a kind a realiser could make, once per sentence where it applies:
//   M1  a correct number written as text instead of a slot
//   M1b a wrong number written as text
//   M2  a value from a fact outside the plan
//   M3  a scale marker replaced by another scale's ("raio" -> "município")
//   M3b two values of one fact at different scales swapped
//   M4  a comparison word inverted
//   M5  a caveat statement removed
//   M6  a causal phrase added
//   M7  a period taken from another fact
std::vector<Mutant> mutate(const std::vector<Paragraph>& paragraphs, const Plan& plan, const std::vector<Fact>& facts,
                           const Language& lang);

// The guard first planned for the thesis: every number in the rendered text must equal a figure
// present in the data. Kept as the baseline the verifier is compared with.
bool numeric_check_passes(const std::string& rendered, const std::vector<Fact>& facts, const Language& lang);

}  // namespace story
