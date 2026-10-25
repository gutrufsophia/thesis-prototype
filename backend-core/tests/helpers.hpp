#pragma once

#include <fstream>
#include <string>

#include <nlohmann/json.hpp>

#include "story/config.hpp"
#include "story/payload.hpp"

namespace test {

inline const story::Config& config() {
    static const story::Config c = story::load_config(STORY_CONFIG_DIR);
    return c;
}

inline story::Payload fixture(const std::string& name) {
    std::ifstream in(std::string(STORY_FIXTURE_DIR) + "/" + name + ".json");
    return story::Payload::from_json(nlohmann::json::parse(in));
}

inline const char* const kFixtures[] = {"padeiros_1000", "hc_1000", "butanta_1000", "poa_1000"};

}  // namespace test
