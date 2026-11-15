"""Agreement and evaluation metrics for the annotation of E2 (content selection) and E4 (text
accuracy), from two annotators' exported files and the system's answers (system.json).

E2  Share of each annotator's 3 picks that the text tells (coverage), against the share expected by
    chance among the statements shown; Jaccard between annotators as the human ceiling; whether the
    lead is picked when it is among the statements shown; facts both annotators picked that the text
    leaves out.
E4  Errors per 100 numeric claims by category (Thomson & Reiter 2020, plus SCALE), for each annotator
    and for the gold list (sentence and category marked by both); sentence-level agreement on whether
    a sentence has an error: Cohen's kappa (Cohen 1960) with the prevalence and bias indices and PABAK
    of Byrt, Bishop & Carlin (1993), and a 95% interval by resampling facilities. The verifier passed
    every text, so each gold error is a verifier miss.

    python3 backend-core/evaluation/annotation/agreement.py anotacao_A.json anotacao_B.json
"""

import argparse
import json
import random
from collections import Counter
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


def load_tasks():
    text = (HERE / "tasks.js").read_text()
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


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
        chance.append(len(planned) / statements[u])  # planned among the statements shown
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
    with_lead = sum(1 for u in units if system[u]["lead"])  # the lead is among the statements shown
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
    by_unit = {u: [(has_error(ann[0], u, s["id"]), has_error(ann[1], u, s["id"])) for s in by_id[u]["sentences"]] for u in units}
    sentence_pairs = [pair for pairs in by_unit.values() for pair in pairs]
    agreement = kappa(sentence_pairs)
    if agreement:
        agreement["kappa_95ci"] = bootstrap_kappa(by_unit)
    return {
        "units": len(units), "sentences": len(sentence_pairs), "claims": claims,
        "annotators": per_annotator,
        "gold": {"errors": len(gold), "per_100_claims": round(100 * len(gold) / claims, 2) if claims else None,
                 "by_category": dict(gold_cats), "verifier_missed": len(gold)},
        "sentence_kappa": agreement,
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
              "e2": e2(tasks, system, ann), "e4": e4(tasks, ann)}
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
