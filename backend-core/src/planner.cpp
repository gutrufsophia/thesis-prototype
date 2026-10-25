#include "story/planner.hpp"

#include <algorithm>
#include <string>

namespace story {

namespace {

const std::vector<std::string> kUnitOrder{"profile", "beds", "staff", "admissions", "stay", "position"};
const std::vector<std::string> kLiving{"sewage", "precarious", "garbage", "crowding", "crowded"};
// Pairs that measure the same thing; at most one of each is told.
const std::vector<std::pair<std::string, std::string>> kOverlapping{{"sewage", "precarious"}, {"crowding", "crowded"}};
// With district data, the district figure replaces the city-wide one.
const std::vector<std::pair<std::string, std::string>> kFinerScale{{"tb_district", "tb"}, {"teen_district", "teen"}};

bool contains(const std::vector<std::string>& list, const std::string& id) {
    return std::find(list.begin(), list.end(), id) != list.end();
}

std::vector<Fact*> by_importance(std::vector<Fact>& facts, const std::vector<std::string>& ids) {
    std::vector<Fact*> out;
    for (auto& f : facts) {
        if (contains(ids, f.id)) out.push_back(&f);
    }
    std::stable_sort(out.begin(), out.end(), [](const Fact* a, const Fact* b) { return a->importance() > b->importance(); });
    return out;
}

}  // namespace

Plan plan_document(std::vector<Fact>& facts, const nlohmann::json& params) {
    const double min_importance = params.at("min_importance").get<double>();
    const auto max_living = params.at("max_living").get<std::size_t>();
    const auto max_outcomes = params.at("max_outcomes").get<std::size_t>();
    const double pair_boost = params.at("pair_boost").get<double>();

    Plan plan;
    plan.paragraphs.resize(3);

    for (const auto& id : kUnitOrder) {
        if (find_fact(facts, id)) plan.paragraphs[0].push_back(id);
    }

    auto& surroundings = plan.paragraphs[1];
    if (find_fact(facts, "residents")) surroundings.push_back("residents");
    std::vector<std::string> living;
    for (Fact* f : by_importance(facts, kLiving)) {
        if (living.size() == max_living || f->importance() < min_importance) break;
        const bool overlaps = std::any_of(kOverlapping.begin(), kOverlapping.end(), [&](const auto& pair) {
            return (f->id == pair.first && contains(living, pair.second)) ||
                   (f->id == pair.second && contains(living, pair.first));
        });
        if (!overlaps) living.push_back(f->id);
    }
    surroundings.insert(surroundings.end(), living.begin(), living.end());

    Fact* network = find_fact(facts, "network");
    Fact* access = find_fact(facts, "access");
    if (network && network->mandatory) {
        surroundings.push_back("network");
        network = nullptr;
    }
    Fact* extra = nullptr;
    for (Fact* candidate : {access, network}) {
        if (candidate && candidate->importance() >= min_importance &&
            (!extra || candidate->importance() > extra->importance())) {
            extra = candidate;
        }
    }
    if (extra) surroundings.push_back(extra->id);

    std::vector<std::string> outcomes;
    for (auto& f : facts) {
        if (f.theme != "outcome") continue;
        const bool replaced = std::any_of(kFinerScale.begin(), kFinerScale.end(), [&](const auto& pair) {
            return f.id == pair.second && find_fact(facts, pair.first);
        });
        if (replaced) continue;
        if (std::any_of(f.pairs_with.begin(), f.pairs_with.end(), [&](const auto& id) { return contains(living, id); })) {
            f.weight *= pair_boost;
        }
        outcomes.push_back(f.id);
    }
    std::vector<std::string> chosen;
    for (Fact* f : by_importance(facts, outcomes)) {
        if (chosen.size() == max_outcomes) break;
        if (!chosen.empty() && f->importance() < min_importance) break;
        chosen.push_back(f->id);
    }
    // District figures first, then the municipality: from the finer scale to the coarser one.
    std::stable_partition(chosen.begin(), chosen.end(), [&](const std::string& id) {
        return find_fact(facts, id)->slots.count("district") > 0;
    });
    plan.paragraphs[2] = chosen;
    return plan;
}

}  // namespace story
