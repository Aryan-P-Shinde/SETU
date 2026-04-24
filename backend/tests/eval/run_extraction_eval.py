"""
Extraction eval runner — run LOCALLY with a real GEMINI_API_KEY.

Usage:
    GEMINI_API_KEY=your-key python tests/eval/run_extraction_eval.py
    GEMINI_API_KEY=your-key python tests/eval/run_extraction_eval.py --id eval_007
    GEMINI_API_KEY=your-key python tests/eval/run_extraction_eval.py --verbose

Scoring:
  - need_type:        20 pts  (exact match or one_of match)
  - urgency_score:    25 pts  (within expected min/max range)
  - affected_count:   15 pts  (exact or within ±20%)
  - skills_needed:    20 pts  (includes all expected skills)
  - location_text:    10 pts  (contains expected substring)
  - contact fields:   10 pts  (name + detail)
  Total: 100 pts per case. Pass threshold: 75/100.
  Suite pass: >85% of cases pass.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.extraction_service import extract_need_fields, SourceChannel

EVAL_FILE = Path(__file__).parent / "extraction_eval_set.json"
PASS_THRESHOLD = 75      # per-case score to pass
SUITE_THRESHOLD = 0.85   # fraction of cases that must pass


def score_case(result, expected: dict) -> tuple[int, list[str]]:
    """Score a single extraction result. Returns (score_0_100, failure_reasons)."""
    score = 0
    failures = []

    # need_type (20 pts)
    got_type = result.need_type.value
    if "need_type" in expected:
        if got_type == expected["need_type"]:
            score += 20
        else:
            failures.append(f"need_type: expected={expected['need_type']} got={got_type}")
    elif "need_type_one_of" in expected:
        if got_type in expected["need_type_one_of"]:
            score += 20
        else:
            failures.append(f"need_type: expected one_of={expected['need_type_one_of']} got={got_type}")

    # urgency_score (25 pts)
    got_urgency = result.urgency_score
    lo = expected.get("urgency_score_min", 0)
    hi = expected.get("urgency_score_max", 10)
    if lo <= got_urgency <= hi:
        score += 25
    else:
        failures.append(f"urgency_score: expected={lo}–{hi} got={got_urgency}")

    # affected_count (15 pts)
    if "affected_count" in expected and expected["affected_count"] is not None:
        exp_count = expected["affected_count"]
        got_count = result.affected_count
        if got_count is not None and abs(got_count - exp_count) / max(exp_count, 1) <= 0.20:
            score += 15
        else:
            failures.append(f"affected_count: expected≈{exp_count} got={got_count}")
    else:
        score += 15  # not tested

    # skills_needed (20 pts)
    if "skills_needed_includes" in expected:
        required = set(expected["skills_needed_includes"])
        got_skills = set(result.skills_needed)
        matched = required & got_skills
        skill_score = int(20 * len(matched) / len(required))
        score += skill_score
        if skill_score < 20:
            failures.append(f"skills: missing={required - got_skills}")
    else:
        score += 20  # not tested

    # location_text (10 pts)
    if "location_text_contains" in expected:
        if expected["location_text_contains"].lower() in result.location_text.lower():
            score += 10
        else:
            failures.append(f"location: expected to contain '{expected['location_text_contains']}' got={result.location_text!r}")
    else:
        score += 10

    # contact fields (10 pts)
    contact_score = 0
    if "contact_name_contains" in expected:
        exp_name = expected["contact_name_contains"]
        got_name = result.contact_name or ""
        if exp_name.lower() in got_name.lower():
            contact_score += 5
        else:
            failures.append(f"contact_name: expected contains '{exp_name}' got={got_name!r}")
    else:
        contact_score += 5

    if "contact_detail_contains" in expected:
        exp_detail = expected["contact_detail_contains"].replace(" ", "")
        got_detail = (result.contact_detail or "").replace(" ", "").replace("-", "")
        if exp_detail in got_detail:
            contact_score += 5
        else:
            failures.append(f"contact_detail: expected contains '{exp_detail}' got={result.contact_detail!r}")
    else:
        contact_score += 5

    score += contact_score

    # Bonus checks (non-scoring but reported)
    if "description_clean_not_contains" in expected:
        if expected["description_clean_not_contains"].lower() in result.description_clean.lower():
            failures.append(f"description_clean: still contains duplicate phrase")

    if "description_clean_max_length" in expected:
        if len(result.description_clean) > expected["description_clean_max_length"]:
            failures.append(f"description_clean too long: {len(result.description_clean)} chars")

    return min(score, 100), failures


async def run_eval(filter_id: str | None = None, verbose: bool = False):
    cases = json.loads(EVAL_FILE.read_text())

    if filter_id:
        cases = [c for c in cases if c["id"] == filter_id]
        if not cases:
            print(f"No case found with id={filter_id}")
            return

    print(f"Running {len(cases)} eval cases against Gemini 1.5 Pro...\n")

    passed = 0
    total_score = 0
    results_log = []

    for case in cases:
        cid = case["id"]
        desc = case["description"]
        inp = case["input"]
        expected = case["expected"]

        t0 = time.perf_counter()
        try:
            result = await extract_need_fields(inp, SourceChannel.text)
            elapsed = time.perf_counter() - t0
            score, failures = score_case(result, expected)
            ok = score >= PASS_THRESHOLD and not result.extraction_failed

            status = "✅ PASS" if ok else "❌ FAIL"
            if ok:
                passed += 1
            total_score += score

            print(f"{status} [{score:3d}/100] [{elapsed:.1f}s] {cid}: {desc}")
            if verbose or not ok:
                print(f"         need_type={result.need_type.value} urgency={result.urgency_score} "
                      f"affected={result.affected_count} skills={result.skills_needed}")
                if failures:
                    for f in failures:
                        print(f"         ⚠ {f}")
                if verbose:
                    print(f"         reasoning: {result.urgency_reasoning[:120]}...")
            print()

        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"❌ ERROR [{elapsed:.1f}s] {cid}: {e}")

        results_log.append({"id": cid, "score": score if 'score' in dir() else 0})

    total = len(cases)
    suite_pass_rate = passed / total
    avg_score = total_score / total

    print("=" * 60)
    print(f"Results: {passed}/{total} cases passed ({suite_pass_rate*100:.0f}%)")
    print(f"Average score: {avg_score:.1f}/100")
    print(f"Target: >{SUITE_THRESHOLD*100:.0f}% pass rate")
    print()
    if suite_pass_rate >= SUITE_THRESHOLD:
        print("✅ SUITE PASS — extraction accuracy meets PRD target")
    else:
        print("❌ SUITE FAIL — consider prompt tuning or model upgrade")
        print("   Hint: Review failed cases above. Common fixes:")
        print("   - Add few-shot examples for failing categories")
        print("   - Adjust urgency score ranges in prompt guide")
        print("   - Check skill taxonomy coverage")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="Run single eval case by ID")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    asyncio.run(run_eval(filter_id=args.id, verbose=args.verbose))
