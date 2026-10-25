#pragma once

#include <vector>

#include "story/config.hpp"
#include "story/model.hpp"
#include "story/payload.hpp"

namespace story {

// Rules that change what may be said (suppress a fact, switch it to another variant).
// They run before planning and may edit the facts.
std::vector<Caveat> apply_pre_rules(const Payload& payload, const Config& config, std::vector<Fact>& facts);

// Rules that add what must be said about the facts that were planned.
std::vector<Caveat> apply_post_rules(const Payload& payload, const Config& config, const std::vector<Fact>& facts,
                                     const Plan& plan);

}  // namespace story
