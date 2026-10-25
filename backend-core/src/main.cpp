#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <optional>
#include <string>

#include <curl/curl.h>
#include <httplib.h>

#include "story/config.hpp"
#include "story/mutation.hpp"
#include "story/narrative.hpp"
#include "story/postgrest.hpp"
#include "story/realiser.hpp"
#include "story/verifier.hpp"

namespace {

std::string env(const char* name, const std::string& fallback = {}) {
    const char* value = std::getenv(name);
    return value && *value ? value : fallback;
}

story::PostgrestClient client_from_env() {
    const auto url = env("SUPABASE_URL");
    const auto key = env("SUPABASE_ANON_KEY");
    if (url.empty() || key.empty()) throw std::runtime_error("SUPABASE_URL and SUPABASE_ANON_KEY must be set");
    return {url, key};
}

double elapsed_ms(std::chrono::steady_clock::time_point since) {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - since).count();
}

int usage() {
    std::cerr << "usage:\n"
                 "  storyteller serve\n"
                 "  storyteller payload CNES RADIUS_M [--public-only]   (prints a fixture)\n"
                 "  storyteller narrate FIXTURE [pt|en] [--text]\n"
                 "  storyteller mutate FIXTURE... (fault-injection table, both languages)\n";
    return 2;
}

int serve(const story::Config& config) {
    const auto client = client_from_env();
    const auto origin = env("ALLOWED_ORIGIN", "*");
    const int port = std::stoi(env("PORT", "8080"));

    // Reference data are loaded on the first request, so the port opens at once on a cold start.
    std::mutex reference_mutex;
    std::optional<story::Reference> reference;
    auto get_reference = [&]() -> const story::Reference& {
        std::lock_guard<std::mutex> lock(reference_mutex);
        if (!reference) reference = client.load_reference();
        return *reference;
    };

    httplib::Server server;
    server.set_default_headers({{"Access-Control-Allow-Origin", origin}, {"Vary", "Origin"}});
    auto send = [](httplib::Response& res, int status, const nlohmann::json& body) {
        res.status = status;
        res.set_content(body.dump(), "application/json; charset=utf-8");
    };

    server.Get("/health", [&](const httplib::Request&, httplib::Response& res) {
        send(res, 200, {{"status", "ok"}, {"version", story::kVersion}});
    });

    server.Get("/narrative", [&](const httplib::Request& req, httplib::Response& res) {
        long long cnes = 0;
        int radius = 1000;
        try {
            cnes = std::stoll(req.get_param_value("cnes"));
            if (req.has_param("radius")) radius = std::stoi(req.get_param_value("radius"));
        } catch (const std::exception&) {
            return send(res, 400, {{"error", "cnes and radius must be integers"}});
        }
        const std::string lang = req.has_param("lang") ? req.get_param_value("lang") : "pt";
        if (!config.languages.count(lang)) return send(res, 400, {{"error", "lang must be pt or en"}});
        const bool public_only = req.get_param_value("public_only") == "1";

        const auto start = std::chrono::steady_clock::now();
        story::Payload payload;
        try {
            payload = client.payload(cnes, radius, public_only, get_reference());
        } catch (const std::invalid_argument& e) {
            return send(res, 404, {{"error", e.what()}});
        } catch (const std::exception& e) {
            return send(res, 502, {{"error", e.what()}});
        }
        const double fetch_ms = elapsed_ms(start);
        const auto generated = std::chrono::steady_clock::now();
        auto body = story::narrate(payload, config, lang);
        body["timing_ms"] = {{"fetch", fetch_ms}, {"generate", elapsed_ms(generated)}};
        if (!body.at("verified").get<bool>()) {
            std::cerr << "verification failed for CNES " << cnes << ": " << body.at("issues").dump() << '\n';
        }
        send(res, 200, body);
    });

    std::cerr << "storyteller " << story::kVersion << " listening on port " << port << '\n';
    return server.listen("0.0.0.0", port) ? 0 : 1;
}

int dump_payload(int argc, char** argv) {
    if (argc < 4) return usage();
    const auto client = client_from_env();
    const bool public_only = argc > 4 && std::string(argv[4]) == "--public-only";
    const auto reference = client.load_reference();
    std::cout << client.payload(std::stoll(argv[2]), std::stoi(argv[3]), public_only, reference).to_json().dump(1)
              << '\n';
    return 0;
}

int narrate_fixture(const story::Config& config, int argc, char** argv) {
    if (argc < 3) return usage();
    std::ifstream in(argv[2]);
    if (!in) {
        std::cerr << "cannot open " << argv[2] << '\n';
        return 1;
    }
    const auto payload = story::Payload::from_json(nlohmann::json::parse(in));
    std::string lang = "pt";
    bool text_only = false;
    for (int i = 3; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--text") {
            text_only = true;
        } else {
            lang = arg;
        }
    }
    const auto body = story::narrate(payload, config, lang);
    if (text_only) {
        std::cout << body.at("text").get<std::string>() << '\n';
        if (!body.at("verified").get<bool>()) std::cerr << "issues: " << body.at("issues").dump(1) << '\n';
    } else {
        std::cout << body.dump(1) << '\n';
    }
    return body.at("verified").get<bool>() ? 0 : 3;
}

// E3: plants every error type in every fixture and counts how many the verifier and the
// numeric-only baseline catch. Originals are checked too, for false positives.
int mutation_table(const story::Config& config, int argc, char** argv) {
    if (argc < 3) return usage();
    struct Count {
        int total = 0, verifier = 0, baseline = 0;
    };
    std::map<std::string, Count> counts;
    nlohmann::json detail = nlohmann::json::array();
    int originals = 0, original_flags = 0, baseline_original_flags = 0;
    for (int i = 2; i < argc; ++i) {
        std::ifstream in(argv[i]);
        const auto payload = story::Payload::from_json(nlohmann::json::parse(in));
        for (const auto& [code, lang] : config.languages) {
            const auto told = story::tell(payload, config, code);
            ++originals;
            if (!story::verify(told.paragraphs, told.plan, told.facts, lang).empty()) ++original_flags;
            if (!story::numeric_check_passes(story::plain_text(story::render(told.paragraphs, told.facts, lang)),
                                             told.facts, lang)) {
                ++baseline_original_flags;
            }
            for (const auto& m : story::mutate(told.paragraphs, told.plan, told.facts, lang)) {
                const auto issues = story::verify(m.paragraphs, told.plan, told.facts, lang);
                const bool caught = !issues.empty();
                const bool baseline = !story::numeric_check_passes(
                    story::plain_text(story::render(m.paragraphs, told.facts, lang)), told.facts, lang);
                auto& c = counts[m.op];
                ++c.total;
                c.verifier += caught;
                c.baseline += baseline;
                nlohmann::json checks = nlohmann::json::array();
                for (const auto& issue : issues) checks.push_back(issue.check);
                detail.push_back({{"fixture", argv[i]}, {"lang", code}, {"op", m.op}, {"detail", m.detail},
                                  {"verifier", caught}, {"checks", checks}, {"baseline", baseline}});
            }
        }
    }
    nlohmann::json table = nlohmann::json::object();
    for (const auto& [op, c] : counts) {
        table[op] = {{"mutants", c.total}, {"verifier", c.verifier}, {"baseline", c.baseline}};
    }
    std::cout << nlohmann::json{{"originals", originals},
                                {"originals_flagged_by_verifier", original_flags},
                                {"originals_flagged_by_baseline", baseline_original_flags},
                                {"operators", table},
                                {"mutants", detail}}
                     .dump(1)
              << '\n';
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) return usage();
    curl_global_init(CURL_GLOBAL_DEFAULT);
    int status = 0;
    try {
        const auto config = story::load_config(env("STORY_CONFIG_DIR", "config"));
        const std::string mode = argv[1];
        if (mode == "serve") {
            status = serve(config);
        } else if (mode == "payload") {
            status = dump_payload(argc, argv);
        } else if (mode == "narrate") {
            status = narrate_fixture(config, argc, argv);
        } else if (mode == "mutate") {
            status = mutation_table(config, argc, argv);
        } else {
            status = usage();
        }
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << '\n';
        status = 1;
    }
    curl_global_cleanup();
    return status;
}
