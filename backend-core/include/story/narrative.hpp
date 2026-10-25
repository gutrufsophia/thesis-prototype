#pragma once

#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "story/config.hpp"
#include "story/model.hpp"
#include "story/payload.hpp"

namespace story {

inline constexpr const char* kVersion = "0.1.0";

struct Story {
    std::vector<Fact> facts;
    Plan plan;
    std::vector<Paragraph> paragraphs;  // still carrying tokens
    std::vector<Caveat> suppressed;
    std::vector<std::string> trimmed;   // facts dropped to fit the length budget
};

// Interpretation -> planning -> realisation (Reiter 2007), for one facility.
Story tell(const Payload& payload, const Config& config, const std::string& lang);

// tell() plus verification and the response sent to the page.
nlohmann::json narrate(const Payload& payload, const Config& config, const std::string& lang);

}  // namespace story
