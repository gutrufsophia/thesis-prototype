"""Agreement and evaluation metrics for the annotation of E2 (content selection) and E4 (text
accuracy), from two or more annotators' exported files and the system's answers (system.json).

E2  Facts left out of the text that should have been told (the recall of the selection): after the
    text, each annotator ticks among up to 6 left-out facts, or "none". Units where a majority saw
    nothing missing; facts a majority would have told, against how often each was shown; ticks per
    unit per annotator; agreement on each shown fact as in E4. The annotators see the text first,
    so this may lean towards the system's choice.
E2b Relevance of what the text tells (the precision of the selection; E2 gives its recall): for
    every sentence each annotator chose "relevant" or "could be left out". Share of sentences a
    strict majority judged relevant, apart for sentences that tell a fact and for caveat sentences,
    which the rules make mandatory; for each fact and each caveat rule, how often a majority would
    leave it out; agreement as in E4 (Fleiss' kappa with interval, Cohen's kappa and PABAK per pair).
    Template texts only: an LLM sentence is judged on its wording as much as on its content.
E4  Errors per 100 numeric claims by category (Thomson & Reiter 2020, plus SCALE), for each annotator
    and for two gold lists: errors (sentence and category) marked by a strict majority, and by at
    least two annotators; apart for the template texts and for the 2 free LLM texts (../llm).
    Sentence-level agreement on whether a sentence has an error, over both kinds of text: Fleiss'
    kappa (Fleiss 1971) over all annotators with a 95% interval by resampling facilities, and Cohen's
    kappa (Cohen 1960) for every pair with the prevalence and bias indices and PABAK of Byrt, Bishop
    & Carlin (1993). The verifier passed every template text, so each gold error in one is a
    verifier miss.

To report results without one annotator (for instance the author), run it again without her file.

    python3 backend-core/evaluation/annotation/agreement.py anotacao_A.json anotacao_B.json [...]
"""

import argparse
import itertools
import json
import random
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20261115
RESAMPLES = 2000


def cohen(pairs):
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


def fleiss(items):
    """Fleiss' kappa for binary ratings; each item is the list of the raters' judgements."""
    if not items:
        return None
    raters = len(items[0])
    yes = [sum(item) for item in items]
    p_yes = sum(yes) / (len(items) * raters)
    agree = [(y * (y - 1) + (raters - y) * (raters - y - 1)) / (raters * (raters - 1)) for y in yes]
    po = sum(agree) / len(items)
    pe = p_yes ** 2 + (1 - p_yes) ** 2
    return (po - pe) / (1 - pe) if pe < 1 else None


def bootstrap(by_unit, statistic):
    """95% percentile interval of a statistic over items, resampling facilities."""
    rng = random.Random(SEED)
    units = list(by_unit)
    values = []
    for _ in range(RESAMPLES):
        value = statistic([item for _ in units for item in by_unit[rng.choice(units)]])
        if value is not None:
            values.append(value)
    values.sort()
    return [round(values[int(0.025 * len(values))], 3), round(values[int(0.975 * len(values)) - 1], 3)] if values else None


def load_tasks():
    text = (HERE / "tasks.js").read_text()
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


def mean(values):
    return round(sum(values) / len(values), 3) if values else None


def e2(tasks, system, ann):
    """Facts left out of the text that the annotators would have told (the recall of the selection)."""
    by_id = {u["id"]: u for u in tasks["units"]}
    units = [u for u in by_id if all(u in a["units"] and a["units"][u].get("done_at") for a in ann)]
    majority = len(ann) // 2 + 1
    picked = lambda a, u, o: o in a["units"][u].get("omitted", [])  # noqa: E731
    by_unit = {u: [[picked(a, u, o["id"]) for a in ann] for o in by_id[u]["omitted"]] for u in units}
    shown, wanted = Counter(), Counter()
    nothing_missing = []
    for u in units:
        votes_none = sum(1 for a in ann if a["units"][u].get("none"))
        nothing_missing.append(votes_none >= majority)
        for o, votes in zip(by_id[u]["omitted"], by_unit[u]):
            fid = system[u]["omitted_fact"][o["id"]]
            shown[fid] += 1
            wanted[fid] += sum(votes) >= majority
    items = [item for rows in by_unit.values() for item in rows]
    pairs = {f"{x['annotator']}-{y['annotator']}": cohen([(item[i], item[j]) for item in items])
             for (i, x), (j, y) in itertools.combinations(enumerate(ann), 2)}
    k = fleiss(items)
    per_annotator = {a["annotator"]: {
        "units_with_nothing_missing": sum(1 for u in units if a["units"][u].get("none")),
        "facts_ticked_per_unit": mean([len(a["units"][u].get("omitted", [])) for u in units]),
    } for a in ann}
    return {
        "units": len(units),
        "left_out_shown": sum(shown.values()),
        "nothing_missing_by_majority": f"{sum(nothing_missing)}/{len(units)}",
        "should_have_been_told_by_majority": {fid: f"{wanted[fid]}/{n}" for fid, n in shown.most_common() if wanted[fid]},
        "annotators": per_annotator,
        "fleiss_kappa": {"kappa": round(k, 3) if k is not None else None, "kappa_95ci": bootstrap(by_unit, fleiss)},
        "cohen_pairs": pairs,
    }


def error_rates(by_id, units, ann):
    """Errors per 100 claims over some units, for each annotator and for the two gold lists."""
    claims = sum(s["claims"] for u in units for s in by_id[u]["sentences"])
    per_100 = lambda n: round(100 * n / claims, 2) if claims else None  # noqa: E731
    per_annotator, votes = {}, Counter()
    for a in ann:
        cats = Counter()
        seen = set()
        for u in units:
            for sid, errors in a["units"][u]["e4"].items():
                for e in errors:
                    cats[e["category"]] += 1
                    seen.add((u, sid, e["category"]))
        votes.update(seen)
        per_annotator[a["annotator"]] = {"errors": sum(cats.values()), "per_100_claims": per_100(sum(cats.values())),
                                         "by_category": dict(cats)}

    def gold(min_votes):
        errors = [k for k, v in votes.items() if v >= min_votes]
        return {"min_annotators": min_votes, "errors": len(errors), "per_100_claims": per_100(len(errors)),
                "by_category": dict(Counter(c for _, _, c in errors))}

    return {"units": len(units), "sentences": sum(len(by_id[u]["sentences"]) for u in units), "claims": claims,
            "annotators": per_annotator, "gold_majority": gold(len(ann) // 2 + 1), "gold_at_least_two": gold(2)}


def e2_relevance(tasks, system, ann):
    by_id = {u["id"]: u for u in tasks["units"]}
    units = [u for u in by_id if system[u].get("condition", "template") == "template"
             and all(u in a["units"] and a["units"][u].get("done_at") for a in ann)]
    majority = len(ann) // 2 + 1
    omit = lambda a, u, s: a["units"][u].get("relevance", {}).get(s) == "omit"  # noqa: E731
    by_unit = {u: [[omit(a, u, s["id"]) for a in ann] for s in by_id[u]["sentences"]] for u in units}
    kept = {"fact": [], "caveat": []}
    left_out = {"fact": Counter(), "caveat": Counter()}
    told = {"fact": Counter(), "caveat": Counter()}
    for u in units:
        for s, votes in zip(by_id[u]["sentences"], by_unit[u]):
            what = system[u]["sentences"][s["id"]]
            kind, keys = ("fact", what["facts"][:1]) if what["facts"] else ("caveat", what["caveats"][:1])
            leave = sum(votes) >= majority
            kept[kind].append(not leave)
            for key in keys:
                told[kind][key] += 1
                left_out[kind][key] += leave
    items = [item for rows in by_unit.values() for item in rows]
    pairs = {f"{x['annotator']}-{y['annotator']}": cohen([(item[i], item[j]) for item in items])
             for (i, x), (j, y) in itertools.combinations(enumerate(ann), 2)}
    k = fleiss(items)
    return {
        "units": len(units),
        "sentences": {kind: len(v) for kind, v in kept.items()},
        "relevant_by_majority": {kind: mean(v) for kind, v in kept.items()},
        "left_out_by_majority": {kind: {key: f"{left_out[kind][key]}/{n}" for key, n in told[kind].most_common()}
                                 for kind in told},
        "fleiss_kappa": {"kappa": round(k, 3) if k is not None else None, "kappa_95ci": bootstrap(by_unit, fleiss)},
        "cohen_pairs": pairs,
    }


def e4(tasks, system, ann):
    by_id = {u["id"]: u for u in tasks["units"]}
    units = [u for u in by_id if all(u in a["units"] and a["units"][u].get("done_at") for a in ann)]
    condition = lambda u: system[u].get("condition", "template")  # noqa: E731

    has_error = lambda a, u, s: bool(a["units"][u]["e4"].get(s))  # noqa: E731
    by_unit = {u: [[has_error(a, u, s["id"]) for a in ann] for s in by_id[u]["sentences"]] for u in units}
    items = [item for rows in by_unit.values() for item in rows]
    pairs = {}
    for (i, x), (j, y) in itertools.combinations(enumerate(ann), 2):
        pairs[f"{x['annotator']}-{y['annotator']}"] = cohen([(item[i], item[j]) for item in items])
    k = fleiss(items)
    return {
        # template texts passed the verifier, so each of their gold errors is a verifier miss
        "template": error_rates(by_id, [u for u in units if condition(u) == "template"], ann),
        "llm_free": error_rates(by_id, [u for u in units if condition(u) == "llm_free"], ann),
        "sentence_fleiss_kappa": {"kappa": round(k, 3) if k is not None else None, "kappa_95ci": bootstrap(by_unit, fleiss)},
        "sentence_cohen_pairs": pairs,
    }


def minutes(ann):
    """Time from opening a unit to concluding it, per annotator: median per unit and total."""
    from datetime import datetime  # noqa: PLC0415

    out = {}
    for a in ann:
        spans = [(datetime.fromisoformat(u["done_at"].replace("Z", "+00:00")) -
                  datetime.fromisoformat(u["started_at"].replace("Z", "+00:00"))).total_seconds() / 60
                 for u in a["units"].values() if u.get("done_at") and u.get("started_at")]
        spans.sort()
        out[a["annotator"]] = {"units": len(spans), "median_per_unit": round(spans[len(spans) // 2], 1) if spans else None,
                               "total": round(sum(spans), 1)}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="the annotators' exported JSON files (two or more)")
    parser.add_argument("--out", type=Path, default=HERE.parent / "results" / "annotation.json")
    args = parser.parse_args()
    if len(args.files) < 2:
        parser.error("agreement needs at least two annotators")
    tasks = load_tasks()
    system = json.loads((HERE / "system.json").read_text())
    ann = [json.loads(f.read_text()) for f in args.files]
    for a in ann:
        if a.get("version") != tasks["version"]:
            raise SystemExit(f"{a.get('annotator')}: annotations made on another version of the tasks")
    result = {"annotators": [a["annotator"] for a in ann], "version": tasks["version"], "minutes": minutes(ann),
              "e2": e2(tasks, system, ann), "e2_relevance": e2_relevance(tasks, system, ann),
              "e4": e4(tasks, system, ann)}
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
