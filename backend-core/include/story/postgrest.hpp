#pragma once

#include <string>

#include <nlohmann/json.hpp>

#include "story/payload.hpp"

namespace story {

// Reads the database through Supabase's REST layer with the public key, like the frontend:
// no database credentials in the service, and row-level security still applies.
class PostgrestClient {
public:
    PostgrestClient(std::string base_url, std::string anon_key);

    nlohmann::json get(const std::string& path) const;
    nlohmann::json rpc(const std::string& function, const nlohmann::json& args) const;

    Reference load_reference() const;
    nlohmann::json facility(long long cnes) const;  // null if unknown
    Payload payload(long long cnes, int radius_m, bool public_only, const Reference& reference) const;

private:
    nlohmann::json request(const std::string& path, const std::string* body) const;

    std::string base_url_;
    std::string anon_key_;
};

}  // namespace story
