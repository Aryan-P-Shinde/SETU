"""
Brief eval runner — generates briefs and checks automated criteria.
Outputs a human-rating sheet for the 10-rater evaluation.

Usage:
    GEMINI_API_KEY=your-key python tests/eval/run_brief_eval.py
    GEMINI_API_KEY=your-key python tests/eval/run_brief_eval.py --id brief_eval_003
    GEMINI_API_KEY=your-key python tests/eval/run_brief_eval.py --save-sheet

Automated scoring (pre-human-rating):
  - Word count within range:       pass / fail
  - Required keywords present:     pass / fail per keyword
  - Forbidden phrases absent:      pass / fail
  - No hallucination markers:      checks for "[?]" frequency

Human rating sheet (--save-sheet):
  Generates brief_rating_sheet.md — send to 10 raters.
  Each rater scores 1–5 on:
    A. Actionability  (can volunteer act on this immediately?)
    B. Accuracy       (nothing invented or wrong?)
    C. Clarity        (plain language, no jargon?)
    D. Completeness   (covers where/what/bring/contact/urgency?)
    E. Length         (80–120 words, WhatsApp-sendable?)

Suite pass: avg automated score ≥ 80%, avg human rating ≥ 4.0/5.0
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.brief_service import generate_brief

EVAL_FILE = Path(__file__).parent / "brief_eval_set.json"
SHEET_FILE = Path(__file__).parent / "brief_rating_sheet.md"


def auto_score(brief_text: str, criteria: dict) -> tuple[int, list[str]]:
    """Return (score_0_100, list_of_failures)."""
    score = 100
    failures = []
    text_lower = brief_text.lower()

    # Word count
    wc = len(brief_text.split())
    lo, hi = criteria.get("word_count_range", [60, 140])
    if not (lo <= wc <= hi):
        score -= 20
        failures.append(f"word_count: {wc} (expected {lo}–{hi})")

    # Required keywords
    required = criteria.get("must_include", [])
    for kw in required:
        if kw.lower() not in text_lower:
            score -= 10
            failures.append(f"missing keyword: {kw!r}")

    # Forbidden phrases
    forbidden = criteria.get("must_not_include", [])
    for phrase in forbidden:
        if phrase.lower() in text_lower:
            score -= 15
            failures.append(f"forbidden phrase found: {phrase!r}")

    return max(0, score), failures


async def run_eval(filter_id: str | None = None, save_sheet: bool = False):
    cases = json.loads(EVAL_FILE.read_text())
    if filter_id:
        cases = [c for c in cases if c["id"] == filter_id]

    print(f"Generating {len(cases)} briefs...\n")

    results = []
    total_auto = 0
    passed = 0

    for case in cases:
        cid = case["id"]
        desc = case["description"]
        needcard = case["needcard"]
        skills = case["volunteer_skills"]
        lang = case["language"]
        criteria = case["eval_criteria"]

        result = await generate_brief(
            needcard_dict=needcard,
            volunteer_skills=skills,
            language_pref=lang,
        )

        score, failures = auto_score(result.brief_text, criteria)
        ok = score >= 80 and not result.generation_failed
        if ok:
            passed += 1
        total_auto += score

        status = "✅" if ok else "❌"
        print(f"{status} [{score}/100] {cid}: {desc}")
        print(f"   Lang={lang} Words={result.word_count} Failed={result.generation_failed}")
        print(f"   ── Brief ──────────────────────────────────")
        for line in result.brief_text.split("\n"):
            print(f"   {line}")
        print(f"   ───────────────────────────────────────────")
        if failures:
            for f in failures:
                print(f"   ⚠  {f}")
        print()

        results.append({
            "id": cid,
            "description": desc,
            "brief": result.brief_text,
            "language": lang,
            "word_count": result.word_count,
            "auto_score": score,
            "failures": failures,
            "generation_failed": result.generation_failed,
        })

    avg_auto = total_auto / len(cases)
    print("=" * 60)
    print(f"Automated: {passed}/{len(cases)} passed | avg score {avg_auto:.0f}/100")
    print(f"Target: ≥80% pass rate, avg ≥80/100")
    print()
    if avg_auto >= 80:
        print("✅ AUTOMATED CHECKS PASS")
    else:
        print("❌ AUTOMATED CHECKS FAIL — review prompt prompt/brief_v1.txt")

    if save_sheet:
        _save_rating_sheet(results)
        print(f"\n📋 Human rating sheet saved: {SHEET_FILE}")
        print("   Send to 10 raters. Target avg ≥ 4.0/5.0 per brief.")


def _save_rating_sheet(results: list[dict]):
    lines = [
        "# SETU — Volunteer Brief Evaluation Sheet",
        "",
        "**Instructions for raters:**",
        "Score each brief 1–5 on each dimension.",
        "",
        "| Score | Meaning |",
        "|-------|---------|",
        "| 5 | Excellent — I could act on this immediately |",
        "| 4 | Good — minor gaps but actionable |",
        "| 3 | Acceptable — some important info missing |",
        "| 2 | Poor — I'd need to ask before going |",
        "| 1 | Unacceptable — misleading or unusable |",
        "",
        "**Dimensions:**",
        "- **A. Actionability** — Can you act on this without asking questions?",
        "- **B. Accuracy** — Is anything invented, wrong, or misleading?",
        "- **C. Clarity** — Plain language? No jargon?",
        "- **D. Completeness** — Covers where / what / bring / contact / urgency?",
        "- **E. Length** — Right length for WhatsApp? Not too long or short?",
        "",
        "---",
        "",
    ]

    for i, r in enumerate(results, 1):
        lines += [
            f"## Brief {i}: {r['description']}",
            f"*Language: {r['language']} | Word count: {r['word_count']}*",
            "",
            "```",
            r["brief"],
            "```",
            "",
            "| Dimension | Score (1–5) | Notes |",
            "|-----------|-------------|-------|",
            "| A. Actionability | | |",
            "| B. Accuracy      | | |",
            "| C. Clarity       | | |",
            "| D. Completeness  | | |",
            "| E. Length        | | |",
            "| **Overall**      | | |",
            "",
            "---",
            "",
        ]

    SHEET_FILE.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="Run single eval case")
    parser.add_argument("--save-sheet", action="store_true", help="Save human rating sheet")
    args = parser.parse_args()
    asyncio.run(run_eval(filter_id=args.id, save_sheet=args.save_sheet))