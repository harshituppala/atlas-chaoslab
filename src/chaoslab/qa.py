"""Compare saved SQuAD-style answers, optionally checking declared source spans.

No application adapter, model invocation or network access. Missing answers count
against every metric. Optional citation sidecars are a CHAOSLAB extension, not
part of the official SQuAD prediction format or leaderboard scoring.
"""

import argparse
import hashlib
import re
import string
from collections import Counter
from pathlib import Path

from .artifacts import publish_report
from .comparison import MAX_BYTES, read_json


def normalize(text):
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return " ".join(re.sub(r"\b(?:a|an|the)\b", " ", text).split())


def answer_scores(answer, references):
    predicted = normalize(answer).split()
    scores = []
    for reference in references:
        expected = normalize(reference).split()
        overlap = sum((Counter(predicted) & Counter(expected)).values())
        f1 = (
            (2 * overlap / (len(predicted) + len(expected)))
            if predicted and expected
            else float(predicted == expected)
        )
        scores.append((float(predicted == expected), f1))
    return max(x[0] for x in scores), max(x[1] for x in scores)


def questions(dataset):
    if not isinstance(dataset, dict) or not isinstance(dataset.get("data"), list):
        raise ValueError("Expected SQuAD data array")
    found = {}
    for article in dataset["data"]:
        if not isinstance(article, dict) or not isinstance(article.get("paragraphs"), list):
            raise ValueError("Expected paragraphs")
        for paragraph in article["paragraphs"]:
            if not isinstance(paragraph, dict):
                raise ValueError("Invalid paragraph")
            context, qas = paragraph.get("context"), paragraph.get("qas")
            if (
                not isinstance(context, str)
                or not 1 <= len(context) <= 100_000
                or not isinstance(qas, list)
            ):
                raise ValueError("Invalid context or questions")
            for qa in qas:
                if not isinstance(qa, dict):
                    raise ValueError("Invalid question")
                key, question, answers = qa.get("id"), qa.get("question"), qa.get("answers")
                if not isinstance(key, str) or not 1 <= len(key) <= 128 or key in found:
                    raise ValueError("Invalid or duplicate question identity")
                if (
                    not isinstance(question, str)
                    or not 1 <= len(question) <= 10_000
                    or not isinstance(answers, list)
                ):
                    raise ValueError("Invalid question or answers")
                impossible = qa.get("is_impossible", False)
                if type(impossible) is not bool or impossible == bool(answers):
                    raise ValueError("Inconsistent answerability")
                if len(answers) > 100:
                    raise ValueError("Too many reference answers")
                for answer in answers:
                    if not isinstance(answer, dict):
                        raise ValueError("Invalid reference answer")
                    text, start = answer.get("text"), answer.get("answer_start")
                    if (
                        not isinstance(text, str)
                        or not text
                        or type(start) is not int
                        or start < 0
                        or context[start : start + len(text)] != text
                    ):
                        raise ValueError("Reference answer does not match context")
                found[key] = {
                    "context": context,
                    "references": [a["text"] for a in answers] or [""],
                }
                if len(found) > 1000:
                    raise ValueError("Question budget exceeded")
    if not found:
        raise ValueError("No questions")
    return found


def admit_predictions(value, items):
    if not isinstance(value, dict) or any(
        k not in items or not isinstance(v, str) or len(v) > 100_000 for k, v in value.items()
    ):
        raise ValueError("Invalid predictions or unknown question")


def admit_citations(value, items):
    if not isinstance(value, dict) or any(k not in items for k in value):
        raise ValueError("Invalid citation identities")
    for citation in value.values():
        if not isinstance(citation, dict) or set(citation) != {"start", "end", "sha256"}:
            raise ValueError("Invalid citation structure")
        if (
            type(citation["start"]) is not int
            or type(citation["end"]) is not int
            or not isinstance(citation["sha256"], str)
        ):
            raise ValueError("Invalid citation types")


def score(items, predictions, citations=None):
    admit_predictions(predictions, items)
    if citations is not None:
        admit_citations(citations, items)
    rows = {}
    for key, item in items.items():
        missing = key not in predictions
        answer = predictions.get(key, "")
        exact, f1 = (0.0, 0.0) if missing else answer_scores(answer, item["references"])
        valid = None
        if citations is not None:
            citation = citations.get(key)
            if missing:
                valid = False
            elif answer == "":
                valid = citation is None
            else:
                context = item["context"]
                valid = (
                    citation is not None
                    and 0 <= citation["start"] < citation["end"] <= len(context)
                    and context[citation["start"] : citation["end"]] == answer
                    and citation["sha256"] == hashlib.sha256(context.encode()).hexdigest()
                )
        rows[key] = {
            "missing": missing,
            "exact": exact,
            "token_f1": f1,
            "citation_valid": valid,
            "passed": exact == 1 and valid is not False,
        }
    return {
        "questions": len(items),
        "missing": sum(r["missing"] for r in rows.values()),
        "exact": sum(r["exact"] for r in rows.values()) / len(items),
        "token_f1": sum(r["token_f1"] for r in rows.values()) / len(items),
        "citation_validity": None
        if citations is None
        else sum(r["citation_valid"] for r in rows.values()) / len(items),
        "rows": rows,
    }


def compare(dataset, reference, candidate, reference_citations=None, candidate_citations=None):
    items = questions(dataset)
    left, right = (
        score(items, reference, reference_citations),
        score(items, candidate, candidate_citations),
    )
    if (reference_citations is None) != (candidate_citations is None):
        raise ValueError("Use citation checking for both runs or neither")
    transitions = {
        name: [] for name in ["both_passed", "both_failed", "improved", "regressed", "unpaired"]
    }
    for key in items:
        a, b = left["rows"][key], right["rows"][key]
        name = (
            "unpaired"
            if a["missing"] or b["missing"]
            else "both_passed"
            if a["passed"] and b["passed"]
            else "both_failed"
            if not a["passed"] and not b["passed"]
            else "regressed"
            if a["passed"]
            else "improved"
        )
        transitions[name].append(key)
    return {
        "schema_version": 1,
        "task": "squad-saved-answer-comparison",
        "reference": left,
        "candidate": right,
        "transitions": transitions,
        "fixture_gate_passed": all(r["passed"] for r in right["rows"].values())
        and not transitions["unpaired"]
        and not transitions["regressed"],
        "limits": [
            "SQuAD-style saved artifacts, not official leaderboard scores or a model execution.",
            "Missing predictions remain in the denominator; no no-answer probability tuning.",
            "Citation sidecars are optional CHAOSLAB extensions; valid source text does not establish answer correctness.",
            "Question IDs are included; review inputs before public report publication.",
        ],
    }


def input_digest(path):
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Input byte budget exceeded")
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["dataset", "reference", "candidate", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ["reference-citations", "candidate-citations"]:
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--require-fixture-gate", action="store_true")
    args = parser.parse_args()
    inputs = [
        args.dataset,
        args.reference,
        args.candidate,
        args.reference_citations,
        args.candidate_citations,
    ]
    try:
        if any(p is not None and args.output.resolve() == p.resolve() for p in inputs):
            raise ValueError("Output must not replace an input")
        before = {str(p): input_digest(p) for p in inputs if p is not None}
        report = compare(*[read_json(p)[1] if p is not None else None for p in inputs])
        if any(input_digest(Path(p)) != digest for p, digest in before.items()):
            raise ValueError("Inputs changed during scoring")
        report["input_sha256"] = {
            label: before[str(p)]
            for label, p in zip(
                ["dataset", "reference", "candidate", "reference_citations", "candidate_citations"],
                inputs,
                strict=True,
            )
            if p is not None
        }
        report["scorer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        publish_report(args.output, report)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        parser.exit(2, "Invalid saved-answer experiment; previous report retained.\n")
    if args.require_fixture_gate and not report["fixture_gate_passed"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
