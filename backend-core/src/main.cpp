#include <cmath>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <optional>
#include <random>
#include <set>
#include <string>
#include <utility>

#include <curl/curl.h>
#include <httplib.h>

#include "story/caveats.hpp"
#include "story/config.hpp"
#include "story/facts.hpp"
#include "story/mutation.hpp"
#include "story/narrative.hpp"
#include "story/planner.hpp"
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
                 "  storyteller payloads RADIUS_M DIR CNES...            (writes DIR/CNES_RADIUS.json)\n"
                 "  storyteller narrate FIXTURE [pt|en] [--text]\n"
                 "  storyteller mutate FIXTURE... (fault-injection table, both languages)\n"
                 "  storyteller triggers FIXTURE... (caveat rules the data trigger, every fact planned)\n"
                 "  storyteller sensitivity FIXTURE... (stability of content selection under parameter changes)\n"
                 "  storyteller caveats FIXTURE [pt|en]                  (wording each planned caveat requires)\n"
                 "  storyteller verify FIXTURE pt|en PARAGRAPHS.json     (verifier on another realiser's text)\n";
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
        send(res, 200, story::servable(std::move(body)));
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

int dump_payloads(int argc, char** argv) {
    if (argc < 5) return usage();
    const auto client = client_from_env();
    const auto reference = client.load_reference();
    const int radius = std::stoi(argv[2]);
    const std::string dir = argv[3];
    int failures = 0;
    for (int i = 4; i < argc; ++i) {
        const std::string path = dir + "/" + argv[i] + "_" + std::to_string(radius) + ".json";
        try {
            const auto payload = client.payload(std::stoll(argv[i]), radius, false, reference);
            {
                std::ofstream out(path + ".tmp");
                out << payload.to_json().dump(1) << '\n';
            }
            std::rename((path + ".tmp").c_str(), path.c_str());
        } catch (const std::exception& e) {
            std::cerr << argv[i] << ": " << e.what() << '\n';
            ++failures;
        }
    }
    return failures ? 1 : 0;
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

story::Payload read_payload(const char* path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error(std::string("cannot open ") + path);
    return story::Payload::from_json(nlohmann::json::parse(in));
}

// LLM comparison: the wording each planned caveat requires, resolved for its fact. Rules the
// templates carry inside the fact's own sentence come out empty.
int caveat_statements(const story::Config& config, int argc, char** argv) {
    if (argc < 3) return usage();
    const std::string code = argc > 3 ? argv[3] : "pt";
    const auto& lang = config.language(code);
    const auto told = story::tell(read_payload(argv[2]), config, code);
    nlohmann::json out = nlohmann::json::array();
    for (const auto& c : told.plan.caveats) {
        if (c.effect == story::Effect::Suppress) continue;
        const auto statement = story::caveat_statement(c, told.facts, lang);
        const auto* text = lang.caveat_for(c.rule, c.variant);
        std::string rendered;
        if (!statement.empty()) {
            rendered = story::plain_text(story::render({{{statement, {}, {c.rule}}}}, told.facts, lang));
        }
        out.push_back({{"rule", c.rule},
                       {"variant", c.variant},
                       {"fact", c.fact},
                       {"effect", c.effect == story::Effect::Disclose ? "disclose" : "qualify"},
                       {"before", c.before},
                       {"statement", rendered},
                       {"marker", text ? text->marker_source : ""}});
    }
    std::cout << out.dump(1) << '\n';
    return 0;
}

// LLM comparison: runs the verifier on paragraphs written by another realiser, given as a JSON
// array of paragraphs, each an array of sentences carrying {fact.field} tokens.
int verify_file(const story::Config& config, int argc, char** argv) {
    if (argc < 5) return usage();
    const std::string code = argv[3];
    const auto& lang = config.language(code);
    const auto told = story::tell(read_payload(argv[2]), config, code);
    std::ifstream in(argv[4]);
    if (!in) throw std::runtime_error(std::string("cannot open ") + argv[4]);
    std::vector<story::Paragraph> paragraphs;
    for (const auto& p : nlohmann::json::parse(in)) {
        story::Paragraph paragraph;
        for (const auto& s : p) paragraph.push_back({s.get<std::string>(), {}, {}});
        paragraphs.push_back(paragraph);
    }
    const auto issues = story::verify(paragraphs, told.plan, told.facts, lang);
    std::cout << nlohmann::json{{"verified", issues.empty()},
                                {"issues", story::to_json(issues)},
                                {"words", story::word_count(paragraphs)}}
                     .dump(1)
              << '\n';
    return 0;
}

// E1 reference: which caveat rules the data trigger when every extracted fact is told, so the
// comparison with annotators measures the rules and not the content selection.
int trigger_table(const story::Config& config, int argc, char** argv) {
    if (argc < 3) return usage();
    nlohmann::json out = nlohmann::json::array();
    for (int i = 2; i < argc; ++i) {
        std::ifstream in(argv[i]);
        const auto payload = story::Payload::from_json(nlohmann::json::parse(in));
        auto facts = story::extract_facts(payload, config.params);
        auto caveats = story::apply_pre_rules(payload, config, facts);
        story::Plan plan;
        plan.paragraphs.resize(4);
        for (const auto& f : facts) {
            const bool unit = f.id == "profile" || f.id == "beds" || f.id == "staff" || f.id == "admissions" ||
                              f.id == "stay" || f.id == "position";
            plan.paragraphs[f.theme == "outcome" ? story::kOutcomes : unit ? story::kUnit : story::kSurroundings].push_back(f.id);
        }
        // finer scale first, as the planner orders outcomes
        auto& outcomes = plan.paragraphs[story::kOutcomes];
        std::stable_partition(outcomes.begin(), outcomes.end(), [&](const std::string& id) {
            const auto* f = story::find_fact(facts, id);
            return f->slots.count("district") > 0 || f->slots.count("observed_district") > 0;
        });
        const auto post = story::apply_post_rules(payload, config, facts, plan);
        caveats.insert(caveats.end(), post.begin(), post.end());
        nlohmann::json rules = nlohmann::json::array();
        for (const auto& c : caveats) rules.push_back({{"rule", c.rule}, {"variant", c.variant}, {"fact", c.fact}});
        nlohmann::json ids = nlohmann::json::array();
        for (const auto& f : facts) ids.push_back(f.id);
        out.push_back({{"fixture", argv[i]}, {"rules", rules}, {"facts", ids}});
    }
    std::cout << out.dump(1) << '\n';
    return 0;
}

// Parameters of content selection chosen by the author. Lexical tiers (wording, not selection),
// the PNAB range (normative) and structural limits are left out. The bound keeps shares below 1.
struct Knob {
    const char* path;
    double max;
    bool integer;
};
const std::vector<Knob> kKnobs{
    {"/saturation_ratio", 1e9, false},   {"/saturation_pp", 1e9, false},       {"/region_weight", 1e9, false},
    {"/theme_weights/living", 1e9, false}, {"/theme_weights/access", 1e9, false}, {"/theme_weights/network", 1e9, false},
    {"/theme_weights/outcome", 1e9, false}, {"/theme_weights/comparison", 1e9, false},
    {"/theme_weights/tension", 1e9, false}, {"/pair_boost", 1e9, false},       {"/district_boost", 1e9, false},
    {"/reliability/low_coverage", 1, false}, {"/reliability/few_tracts", 1, false},
    {"/reliability/approximate_position", 1, false}, {"/min_importance", 1e9, false},
    {"/peer_extreme", 0.99, false},      {"/need_high", 0.99, false},           {"/rank_extreme", 0.49, false},
    {"/casemix_min_shift", 1e9, false},  {"/casemix_second", 1, false},
};

struct Told {
    std::set<std::string> facts;
    std::string lead;
    std::set<std::string> caveats;
};

Told told_with(const story::Payload& payload, const story::Config& config) {
    const auto s = story::tell(payload, config, "pt");
    Told t;
    for (const auto& paragraph : s.plan.paragraphs) t.facts.insert(paragraph.begin(), paragraph.end());
    if (!s.plan.paragraphs[story::kLead].empty()) t.lead = s.plan.paragraphs[story::kLead].front();
    for (const auto& c : s.plan.caveats) t.caveats.insert(c.rule);
    return t;
}

double jaccard(const std::set<std::string>& a, const std::set<std::string>& b) {
    if (a.empty() && b.empty()) return 1;
    std::size_t both = 0;
    for (const auto& x : a) both += b.count(x);
    return static_cast<double>(both) / static_cast<double>(a.size() + b.size() - both);
}

story::Config scaled(const story::Config& base, const std::vector<double>& factors) {
    story::Config c = base;
    for (std::size_t i = 0; i < kKnobs.size(); ++i) {
        const nlohmann::json::json_pointer ptr(kKnobs[i].path);
        double v = std::min(c.params.at(ptr).get<double>() * factors[i], kKnobs[i].max);
        c.params[ptr] = kKnobs[i].integer ? std::round(v) : v;
    }
    return c;
}

// How much the text's content changes when the selection parameters change: each parameter at
// 0.5x and 1.5x alone, then all of them drawn uniformly in [0.5, 1.5] at once (fixed seed).
int sensitivity_table(const story::Config& config, int argc, char** argv) {
    if (argc < 3) return usage();
    std::vector<story::Payload> payloads;
    std::vector<Told> base;
    for (int i = 2; i < argc; ++i) {
        std::ifstream in(argv[i]);
        payloads.push_back(story::Payload::from_json(nlohmann::json::parse(in)));
        base.push_back(told_with(payloads.back(), config));
    }
    auto compare = [&](const story::Config& c) {
        double facts = 0, caveats = 0, worst = 1;
        int same = 0, lead = 0;
        for (std::size_t i = 0; i < payloads.size(); ++i) {
            const auto t = told_with(payloads[i], c);
            const double j = jaccard(t.facts, base[i].facts);
            facts += j;
            worst = std::min(worst, j);
            caveats += jaccard(t.caveats, base[i].caveats);
            same += t.facts == base[i].facts;
            lead += t.lead == base[i].lead;
        }
        const double n = static_cast<double>(payloads.size());
        return nlohmann::json{{"jaccard_facts", facts / n}, {"min_jaccard_facts", worst},
                              {"jaccard_caveats", caveats / n}, {"same_facts_share", same / n},
                              {"same_lead_share", lead / n}};
    };

    nlohmann::json one_at_a_time = nlohmann::json::object();
    for (std::size_t k = 0; k < kKnobs.size(); ++k) {
        nlohmann::json row = nlohmann::json::object();
        for (double f : {0.5, 1.5}) {
            std::vector<double> factors(kKnobs.size(), 1.0);
            factors[k] = f;
            row[f < 1 ? "x0.5" : "x1.5"] = compare(scaled(config, factors));
        }
        one_at_a_time[kKnobs[k].path] = row;
    }

    const int draws = 500;
    std::mt19937 rng(20261122);
    std::uniform_real_distribution<double> unit(0.5, 1.5);
    std::vector<double> facts, leads, same, caveats;
    for (int d = 0; d < draws; ++d) {
        std::vector<double> factors(kKnobs.size());
        for (auto& f : factors) f = unit(rng);
        const auto r = compare(scaled(config, factors));
        facts.push_back(r.at("jaccard_facts"));
        leads.push_back(r.at("same_lead_share"));
        same.push_back(r.at("same_facts_share"));
        caveats.push_back(r.at("jaccard_caveats"));
    }
    auto summary = [](std::vector<double> v) {
        std::sort(v.begin(), v.end());
        double mean = 0;
        for (double x : v) mean += x;
        mean /= static_cast<double>(v.size());
        auto at = [&](double q) { return v[static_cast<std::size_t>(q * (v.size() - 1))]; };
        return nlohmann::json{{"mean", mean}, {"p05", at(0.05)}, {"median", at(0.5)}, {"p95", at(0.95)}};
    };
    std::cout << nlohmann::json{{"facilities", payloads.size()},
                                {"one_at_a_time", one_at_a_time},
                                {"joint", {{"draws", draws},
                                           {"jaccard_facts", summary(facts)},
                                           {"same_facts_share", summary(same)},
                                           {"same_lead_share", summary(leads)},
                                           {"jaccard_caveats", summary(caveats)}}}}
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
        } else if (mode == "payloads") {
            status = dump_payloads(argc, argv);
        } else if (mode == "narrate") {
            status = narrate_fixture(config, argc, argv);
        } else if (mode == "mutate") {
            status = mutation_table(config, argc, argv);
        } else if (mode == "sensitivity") {
            status = sensitivity_table(config, argc, argv);
        } else if (mode == "caveats") {
            status = caveat_statements(config, argc, argv);
        } else if (mode == "verify") {
            status = verify_file(config, argc, argv);
        } else if (mode == "triggers") {
            status = trigger_table(config, argc, argv);
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
