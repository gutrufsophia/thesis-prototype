#pragma once

#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "story/config.hpp"
#include "story/model.hpp"
#include "story/payload.hpp"

namespace story {

inline constexpr const char* kVersion = "0.3.5";

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

// What the service sends: a text that failed verification is withheld; the facts stay for the page's cards.
nlohmann::json servable(nlohmann::json body);

}  // namespace story
