"""
Integration tests for Whisper transcription — run LOCALLY only.

Usage:
    python tests/integration/test_whisper_real.py

Requires:
    - openai-whisper installed (pip install openai-whisper)
    - Test audio files in tests/fixtures/audio/

Scoring rubric (WER = Word Error Rate):
    - Excellent: WER < 10%
    - Acceptable: WER < 20%
    - Failing: WER >= 20%
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# 20 test cases per PRD — mix of Hindi, Bengali, English, code-switching, quality levels
TEST_CASES = [
    # (filename, expected_language, expected_keywords, quality_note)
    ("hindi_clear_01.wav",   "hi", ["खाना", "पानी"],           "clear studio quality"),
    ("hindi_clear_02.wav",   "hi", ["अस्पताल", "दवाई"],        "clear, medical terms"),
    ("hindi_noisy_01.wav",   "hi", ["बाढ़", "लोग"],             "background noise"),
    ("hindi_noisy_02.wav",   "hi", ["बचाव", "मदद"],            "crowd noise"),
    ("hindi_phone_01.wav",   "hi", ["घर", "परिवार"],           "phone call quality"),
    ("bengali_clear_01.wav", "bn", ["বন্যা", "মানুষ"],          "clear"),
    ("bengali_clear_02.wav", "bn", ["খাবার", "পানি"],          "clear, food terms"),
    ("bengali_noisy_01.wav", "bn", ["সাহায্য", "দরকার"],       "street noise"),
    ("bengali_phone_01.wav", "bn", ["ডাক্তার"],                "phone quality"),
    ("english_clear_01.wav", "en", ["shelter", "families"],    "clear"),
    ("english_clear_02.wav", "en", ["medical", "urgent"],      "clear, urgent"),
    ("english_noisy_01.wav", "en", ["flood", "people"],        "rain background"),
    ("english_phone_01.wav", "en", ["help", "water"],          "phone quality"),
    ("code_switch_01.wav",   "hi", ["need", "madad"],          "Hinglish code-switch"),
    ("code_switch_02.wav",   "hi", ["doctor", "chahiye"],      "Hinglish medical"),
    ("code_switch_bn_01.wav","bn", ["help", "দরকার"],          "Bengali-English switch"),
    ("low_quality_01.wav",   "hi", [],                         "very degraded, any output ok"),
    ("low_quality_02.wav",   "en", [],                         "cracked screen recording sim"),
    ("whatsapp_forward_01.wav","hi",["बाढ़"],                  "WhatsApp compressed audio"),
    ("whatsapp_forward_02.wav","en",["rescue"],                "WhatsApp compressed audio"),
]

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "../fixtures/audio")


def run_tests():
    try:
        import whisper
    except ImportError:
        print("❌ openai-whisper not installed. Run: pip install openai-whisper")
        sys.exit(1)

    model_name = os.getenv("WHISPER_MODEL", "base")
    print(f"Loading Whisper model: {model_name}")
    model = whisper.load_model(model_name)

    results = []
    passed = 0

    for filename, expected_lang, expected_keywords, note in TEST_CASES:
        filepath = os.path.join(FIXTURES_DIR, filename)

        if not os.path.exists(filepath):
            print(f"  ⚠️  SKIP  {filename} (file not found — add real recording here)")
            continue

        t0 = time.perf_counter()
        result = model.transcribe(filepath, language=None, temperature=0)
        elapsed = time.perf_counter() - t0

        detected = result["language"]
        transcript = result["text"].strip().lower()

        lang_ok = detected == expected_lang
        kw_ok = all(kw.lower() in transcript for kw in expected_keywords) if expected_keywords else True
        ok = lang_ok and kw_ok

        status = "✅ PASS" if ok else "❌ FAIL"
        if ok:
            passed += 1

        results.append(ok)
        print(
            f"  {status}  [{elapsed:.1f}s]  {filename}\n"
            f"         lang: expected={expected_lang} got={detected}  {'✓' if lang_ok else '✗'}\n"
            f"         transcript: {transcript[:80]}\n"
            f"         note: {note}\n"
        )

    total = len(results)
    if total == 0:
        print("\n⚠️  No test files found. Add real recordings to tests/fixtures/audio/")
        return

    pct = passed / total * 100
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed ({pct:.0f}%)")
    print(f"Target: >85% (PRD requirement)")
    print("PASS ✅" if pct >= 85 else "FAIL ❌ — consider upgrading to 'small' model")


if __name__ == "__main__":
    run_tests()