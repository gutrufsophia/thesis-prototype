#include "story/postgrest.hpp"

#include <algorithm>
#include <memory>
#include <stdexcept>

#include <curl/curl.h>

namespace story {

namespace {

std::size_t collect(char* data, std::size_t size, std::size_t count, void* out) {
    static_cast<std::string*>(out)->append(data, size * count);
    return size * count;
}

}  // namespace

PostgrestClient::PostgrestClient(std::string base_url, std::string anon_key)
    : base_url_(std::move(base_url)), anon_key_(std::move(anon_key)) {
    while (!base_url_.empty() && base_url_.back() == '/') base_url_.pop_back();
}

nlohmann::json PostgrestClient::request(const std::string& path, const std::string* body) const {
    std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> curl(curl_easy_init(), curl_easy_cleanup);
    if (!curl) throw std::runtime_error("curl_easy_init failed");

    const std::string url = base_url_ + "/rest/v1/" + path;
    std::string response;
    curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, ("apikey: " + anon_key_).c_str());
    headers = curl_slist_append(headers, ("Authorization: Bearer " + anon_key_).c_str());
    headers = curl_slist_append(headers, "Content-Type: application/json");
    std::unique_ptr<curl_slist, decltype(&curl_slist_free_all)> header_list(headers, curl_slist_free_all);

    curl_easy_setopt(curl.get(), CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl.get(), CURLOPT_HTTPHEADER, header_list.get());
    curl_easy_setopt(curl.get(), CURLOPT_WRITEFUNCTION, collect);
    curl_easy_setopt(curl.get(), CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl.get(), CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl.get(), CURLOPT_NOSIGNAL, 1L);
    if (body) {
        curl_easy_setopt(curl.get(), CURLOPT_POST, 1L);
        curl_easy_setopt(curl.get(), CURLOPT_POSTFIELDS, body->c_str());
        curl_easy_setopt(curl.get(), CURLOPT_POSTFIELDSIZE, static_cast<long>(body->size()));
    }

    const CURLcode code = curl_easy_perform(curl.get());
    if (code != CURLE_OK) throw std::runtime_error(std::string("request failed: ") + curl_easy_strerror(code));
    long status = 0;
    curl_easy_getinfo(curl.get(), CURLINFO_RESPONSE_CODE, &status);
    if (status >= 400) throw std::runtime_error("HTTP " + std::to_string(status) + " from " + path + ": " + response);
    return nlohmann::json::parse(response);
}

nlohmann::json PostgrestClient::get(const std::string& path) const { return request(path, nullptr); }

nlohmann::json PostgrestClient::rpc(const std::string& function, const nlohmann::json& args) const {
    const std::string body = args.dump();
    return request("rpc/" + function, &body);
}

Reference PostgrestClient::load_reference() const {
    Reference r;
    for (const auto& row : rpc("municipal_indicators", nlohmann::json::object())) r.municipalities.push_back(row);
    for (const auto& row : rpc("district_indicators", nlohmann::json::object())) r.districts.push_back(row);
    for (const auto& row : get("infraestrutura_saude?select=media_dias_permanencia&internacoes_total=gt.0")) {
        if (row.at("media_dias_permanencia").is_number()) r.hospital_stays.push_back(row.at("media_dias_permanencia"));
    }
    std::sort(r.hospital_stays.begin(), r.hospital_stays.end());
    return r;
}

nlohmann::json PostgrestClient::facility(long long cnes) const {
    const auto rows = get("infraestrutura_saude?CO_CNES=eq." + std::to_string(cnes) + "&select=*");
    return rows.empty() ? nlohmann::json() : rows.front();
}

Payload PostgrestClient::payload(long long cnes, int radius_m, bool public_only, const Reference& reference) const {
    auto row = facility(cnes);
    if (row.is_null()) throw std::invalid_argument("unknown CNES " + std::to_string(cnes));
    auto surroundings = rpc("facility_surroundings", {{"p_cnes", cnes}, {"p_radius_m", radius_m}});
    if (!surroundings.value("located", false)) throw std::invalid_argument("facility has no position");
    return assemble(std::move(row), std::move(surroundings), reference, public_only);
}

}  // namespace story
