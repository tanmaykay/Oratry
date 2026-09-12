"""Frozen representative cases for prompt-evaluator calibration.

These are test inputs, not gold scores. Human raters should add versioned gold
labels before using them to accept a provider/model change.
"""

from schemas.evaluation import EvaluationInput


CHALLENGE = "Explain whether your team should adopt a four-day workweek. Give a position, two reasons, and a conclusion."
PROMPT = "Speak for about 90 seconds to a mixed team of managers and staff."


def example(name: str, transcript: str, metrics: dict, expected_focus: str, notes: str) -> dict:
    return {
        "id": name,
        "input": EvaluationInput(CHALLENGE, PROMPT, "structure", transcript, metrics,
                                 ["pilot", "productivity", "coverage"], None, {"structure": "developing"}),
        "expected_primary_weakness": expected_focus,
        "rater_notes": notes,
    }


EXAMPLES = (
    example("excellent_structured_answer",
        "I support a four-day workweek pilot. First, a focused pilot can protect productivity by measuring output, not hours. Second, planned coverage keeps customers supported. In conclusion, run a three-month pilot, review the data, and keep it only if service and output hold steady.",
        {"duration_seconds": 88, "word_count": 43, "words_per_minute": 129, "filler_count": 0, "pause_count": 3},
        "language", "Expect strong structure and clarity; do not penalize concise length."),
    example("rambling_answer",
        "A four-day week is interesting because people have talked about it for a long time and there are many ways to look at it, and on the one hand people like time off, but work is also important, and different teams may do different things, so I think we should think about it carefully and maybe see what happens.",
        {"duration_seconds": 91, "word_count": 57, "words_per_minute": 151, "filler_count": 0, "pause_count": 1},
        "structure", "Expect low structure: no clear position, two reasons, or conclusion."),
    example("filler_heavy_answer",
        "Um, I support, uh, a pilot because, like, it could help productivity. Um, we should, you know, keep coverage. Uh, so, like, maybe try it and see.",
        {"duration_seconds": 45, "word_count": 31, "words_per_minute": 41, "filler_count": 8, "filler_rate": 0.258, "pause_count": 9},
        "fluency", "Expect fluency focus from explicit filler and pause measurements."),
    example("extremely_fast_answer",
        "I support a pilot because productivity can be measured and coverage can be planned, so run it for three months, compare output and service levels, then decide whether to continue.",
        {"duration_seconds": 20, "word_count": 31, "words_per_minute": 240, "filler_count": 0, "pause_count": 0},
        "delivery", "Expect delivery/pace concern without claims about stress or confidence."),
    example("very_slow_answer",
        "I support a pilot. It may improve productivity. We can plan coverage. In conclusion, test it for three months.",
        {"duration_seconds": 120, "word_count": 21, "words_per_minute": 11, "filler_count": 0, "pause_count": 15, "pause_seconds": 72},
        "delivery", "Expect delivery/pace concern based on metrics, not voice quality."),
    example("strong_vocabulary_poor_structure",
        "The proposal has compelling operational ramifications, and productivity is a salient consideration. Coverage is consequential. A pilot may be advantageous, although workforce autonomy and organizational elasticity are also relevant.",
        {"duration_seconds": 74, "word_count": 29, "words_per_minute": 141, "filler_count": 0, "pause_count": 2},
        "structure", "Do not reward sophisticated vocabulary for missing position, reasons, and conclusion."),
    example("simple_vocabulary_excellent_communication",
        "I support a four-day pilot. First, people can focus on the work that matters, so we can check whether output stays strong. Second, each team can plan who answers customers each day. In conclusion, test it for three months and keep it only if both results are good.",
        {"duration_seconds": 82, "word_count": 45, "words_per_minute": 133, "filler_count": 0, "pause_count": 3},
        "language", "Simple words should still permit high clarity and language scores."),
    example("non_native_english",
        "I support the pilot. First, it give workers more rest and they can focus better. Second, our team can make coverage plan for customers. In conclusion, we test for three months and check the results.",
        {"duration_seconds": 78, "word_count": 38, "words_per_minute": 112, "filler_count": 0, "pause_count": 4},
        "language", "Assess only transcript-visible grammar/precision; never mention accent or nativeness."),
    example("short_incomplete_answer",
        "I support a four-day workweek because people need rest.",
        {"duration_seconds": 10, "word_count": 10, "words_per_minute": 60, "filler_count": 0, "pause_count": 0},
        "structure", "Expect challenge-completion/structure issue; do not invent a second reason."),
    example("off_topic_answer",
        "I enjoy working from home because my commute is long and I can cook lunch. My apartment is quieter in the morning. In conclusion, remote work is useful for me.",
        {"duration_seconds": 57, "word_count": 30, "words_per_minute": 126, "filler_count": 0, "pause_count": 2},
        "clarity", "Expect directness/relevance penalty because it does not answer the assigned challenge."),
    example("repeated_self_correcting_answer",
        "I support a pilot because it helps productivity, productivity, I mean it may help people focus. The second reason is coverage, or rather, coverage needs a plan. In conclusion, test it, test it for three months.",
        {"duration_seconds": 66, "word_count": 37, "words_per_minute": 134, "filler_count": 0, "pause_count": 6},
        "fluency", "Expect repetition/self-correction to affect fluency, while preserving its basic structure."),
    )
