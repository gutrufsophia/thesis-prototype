"""Agreement and evaluation metrics for the annotation of E1 (caveats), E2 (content selection) and
E4 (text accuracy), from two annotators' exported files and the system's answers (system.json).

E1  Cohen's kappa between annotators (Cohen 1960) with the prevalence and bias indices and PABAK of
    Byrt, Bishop & Carlin (1993), pooled over facility x rule items and per rule; a 95% interval by
    resampling facilities. The rules are scored against the items both annotators agree on
    (precision, recall, F1) and against each annotator (kappa).
E2  Share of each annotator's chosen statements that the text tells (coverage), against the share
    expected by chance; Jaccard between annotators as the human ceiling; whether the lead is chosen;
    facts both annotators chose that the text leaves out.
E4  Errors per 100 numeric claims by category (Thomson & Reiter 2020, plus SCALE), for each annotator
    and for the gold list (sentence and category marked by both); sentence-level kappa on whether a
    sentence has an error. The verifier passed every text, so each gold error is a verifier miss.

    python3 backend-core/evaluation/annotation/agreement.py anotacao_A.json anotacao_B.json
"""

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20261115
RESAMPLES = 2000


def kappa(pairs):
    """Cohen's kappa, observed agreement, prevalence and bias indices and PABAK for binary pairs."""
    n = len(pairs)
    if not n:
        return None
    a = sum(1 for x, y in pairs if x and y)
    d = sum(1 for x, y in pairs if not x and not y)
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if not x and y)
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / n ** 2
    return {
        "n": n,
        "observed": round(po, 3),
        "kappa": round((po - pe) / (1 - pe), 3) if pe < 1 else None,
        "pabak": round(2 * po - 1, 3),
        "prevalence_index": round(abs(a - d) / n, 3),
        "bias_index": round(abs(b - c) / n, 3),
        "positives": [a + b, a + c],
    }


def bootstrap_kappa(by_unit):
    """95% percentile interval for the pooled kappa, resampling facilities."""
    rng = random.Random(SEED)
    units = list(by_unit)
    values = []
    for _ in range(RESAMPLES):
        sample = [pair for _ in units for pair in by_unit[rng.choice(units)]]
        k = kappa(sample)["kappa"]
        if k is not None:
            values.append(k)
    values.sort()
    return [round(values[int(0.025 * len(values))], 3), round(values[int(0.975 * len(values)) - 1], 3)] if values else None


def prf(pairs):
    """System (first) against reference (second)."""
    tp = sum(1 for s, r in pairs if s and r)
    fp = sum(1 for s, r in pairs if s and not r)
    fn = sum(1 for s, r in pairs if not s and r)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    rnd = lambda v: round(v, 3) if v is not None else None  # noqa: E731
    return {"tp": tp, "fp": fp, "fn": fn, "precision": rnd(precision), "recall": rnd(recall), "f1": rnd(f1)}


def load_tasks():
    text = (HERE / "tasks.js").read_text()
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


def e1(tasks, system, ann):
    rules = [item["id"] for item in tasks["checklist"]]
    units = [u for u in system if all(u in a["units"] and a["units"][u].get("locked_at") for a in ann)]
    yes = lambda a, u, r: a["units"][u]["e1"].get(r) == "sim"  # noqa: E731
    pooled, by_unit = [], defaultdict(list)
    for u in units:
        for r in rules:
            pair = (yes(ann[0], u, r), yes(ann[1], u, r))
            pooled.append(pair)
            by_unit[u].append(pair)
    overall = kappa(pooled)
    if overall:
        overall["kappa_95ci"] = bootstrap_kappa(by_unit)
    per_rule = {}
    consensus_pairs = []
    for r in rules:
        pairs = [(yes(ann[0], u, r), yes(ann[1], u, r)) for u in units]
        agreed = [(system[u]["rules"][r], yes(ann[0], u, r)) for u in units if yes(ann[0], u, r) == yes(ann[1], u, r)]
        consensus_pairs += agreed
        per_rule[r] = {
            "annotators": kappa(pairs),
            "system_positives": sum(system[u]["rules"][r] for u in units),
            "system_vs_consensus": prf(agreed),
            "system_vs_each": [kappa([(system[u]["rules"][r], yes(a, u, r)) for u in units]) for a in ann],
        }
    return {"units": len(units), "annotators": overall, "system_vs_consensus": prf(consensus_pairs), "per_rule": per_rule}


def e2(tasks, system, ann):
    statements = {u["id"]: len(u["statements"]) for u in tasks["units"]}
    units = [u for u in system if all(u in a["units"] and a["units"][u].get("locked_at") for a in ann)]
    coverage = [[], []]
    chance, jaccard, consensus_recall = [], [], []
    lead_hits = [0, 0, 0]
    missed = Counter()
    for u in units:
        planned = set(system[u]["planned"])
        chosen = [set(a["units"][u]["e2"]) for a in ann]
        for i, c in enumerate(chosen):
            coverage[i].append(len(c & planned) / len(c))
        chance.append(len(planned) / statements[u])
        both = chosen[0] & chosen[1]
        jaccard.append(len(both) / len(chosen[0] | chosen[1]))
        if both:
            consensus_recall.append(len(both & planned) / len(both))
        lead = system[u]["lead"]
        if lead:
            lead_hits[0] += lead in chosen[0]
            lead_hits[1] += lead in chosen[1]
            lead_hits[2] += lead in both
        for s in both - planned:
            missed[system[u]["statement_fact"][s]] += 1
    mean = lambda v: round(sum(v) / len(v), 3) if v else None  # noqa: E731
    with_lead = sum(1 for u in units if system[u]["lead"])
    return {
        "units": len(units),
        "coverage": [mean(c) for c in coverage],
        "coverage_by_chance": mean(chance),
        "jaccard_annotators": mean(jaccard),
        "consensus_told": mean(consensus_recall),
        "lead_chosen": {"units_with_lead": with_lead, "annotator_1": lead_hits[0], "annotator_2": lead_hits[1], "both": lead_hits[2]},
        "chosen_by_both_but_not_told": dict(missed.most_common()),
    }


def e4(tasks, ann):
    by_id = {u["id"]: u for u in tasks["units"]}
    units = [u for u in by_id if all(u in a["units"] and a["units"][u].get("done_at") for a in ann)]
    claims = sum(s["claims"] for u in units for s in by_id[u]["sentences"])
    per_annotator, marks = [], []
    for a in ann:
        cats = Counter()
        seen = set()
        for u in units:
            for sid, errors in a["units"][u]["e4"].items():
                for e in errors:
                    cats[e["category"]] += 1
                    seen.add((u, sid, e["category"]))
        marks.append(seen)
        total = sum(cats.values())
        per_annotator.append({"errors": total, "per_100_claims": round(100 * total / claims, 2) if claims else None,
                              "by_category": dict(cats)})
    gold = marks[0] & marks[1]
    gold_cats = Counter(c for _, _, c in gold)
    has_error = lambda a, u, s: bool(a["units"][u]["e4"].get(s))  # noqa: E731
    sentence_pairs = [(has_error(ann[0], u, s["id"]), has_error(ann[1], u, s["id"])) for u in units for s in by_id[u]["sentences"]]
    return {
        "units": len(units), "sentences": len(sentence_pairs), "claims": claims,
        "annotators": per_annotator,
        "gold": {"errors": len(gold), "per_100_claims": round(100 * len(gold) / claims, 2) if claims else None,
                 "by_category": dict(gold_cats), "verifier_missed": len(gold)},
        "sentence_kappa": kappa(sentence_pairs),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs=2, type=Path, help="the two annotators' exported JSON files")
    parser.add_argument("--out", type=Path, default=HERE.parent / "results" / "annotation.json")
    args = parser.parse_args()
    tasks = load_tasks()
    system = json.loads((HERE / "system.json").read_text())
    ann = [json.loads(f.read_text()) for f in args.files]
    for a in ann:
        if a.get("version") != tasks["version"]:
            raise SystemExit(f"{a.get('annotator')}: annotations made on another version of the tasks")
    result = {"annotators": [a["annotator"] for a in ann], "version": tasks["version"],
              "e1": e1(tasks, system, ann), "e2": e2(tasks, system, ann), "e4": e4(tasks, ann)}
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "e1"} | {"e1": {k: v for k, v in result["e1"].items() if k != "per_rule"}},
                     indent=1, ensure_ascii=False))
    print(f"\nPer-rule detail and the rest in {args.out}")


if __name__ == "__main__":
    main()
