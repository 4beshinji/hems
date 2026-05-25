"""Self-contained intervention efficacy logic (ported from SOMS Group D).

hems measures *its own* effect on the environment: when it creates an
environment task ("換気して", "エアコンつけて"), did the targeted metric move
toward its comfort band after the task was completed? This module holds the
two pure pieces of that loop — deriving which metric a task targets, and
turning a (baseline, post) pair into a verdict. Both are side-effect free and
unit-tested; the DB plumbing lives in event_store + the brain eval loop.
"""

# Comfort bands per actionable metric, plus a noise floor (min_delta): a
# baseline->post move smaller than min_delta (in distance-to-band terms) is
# treated as inconclusive rather than crediting/blaming the intervention.
METRIC_SPECS = {
    "temperature": {"lo": 18.0, "hi": 26.0, "min_delta": 0.5},
    "co2": {"lo": 0.0, "hi": 1000.0, "min_delta": 50.0},
    "humidity": {"lo": 30.0, "hi": 60.0, "min_delta": 3.0},
}

# Keyword -> metric, checked in order so a specific signal (換気=co2) is not
# stolen by a generic temperature keyword.
_METRIC_KEYWORDS = [
    ("co2", ["co2", "換気", "二酸化炭素"]),
    ("humidity", ["湿度", "加湿", "除湿"]),
    ("temperature", ["温度", "室温", "気温", "暑", "寒", "冷房", "暖房", "冷", "暖", "エアコン", "空調"]),
]


def derive_trigger_metric(text: str) -> str | None:
    """Return the environment metric a task targets, or None if it isn't an
    environment task we can measure (those are not tracked for efficacy)."""
    if not text:
        return None
    lowered = text.lower()
    for metric, keywords in _METRIC_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return metric
    return None


def _dist_to_band(value: float, lo: float, hi: float) -> float:
    """Distance from a value to the comfort band [lo, hi]; 0 if inside."""
    if value < lo:
        return lo - value
    if value > hi:
        return value - hi
    return 0.0


def compute_verdict(metric: str, baseline: float | None, post: float | None) -> str:
    """Verdict on whether the metric improved between baseline and post.

    "effective" = moved toward (or into) the comfort band by more than the
    metric's noise floor. Direction-agnostic, so it handles both high and low
    excursions (too hot vs. too cold) without a stored direction.

    Returns one of: 'effective', 'counterproductive', 'inconclusive'.
    """
    spec = METRIC_SPECS.get(metric)
    if spec is None or baseline is None or post is None:
        return "inconclusive"
    base_dist = _dist_to_band(baseline, spec["lo"], spec["hi"])
    post_dist = _dist_to_band(post, spec["lo"], spec["hi"])
    improvement = base_dist - post_dist  # >0 means closer to comfort
    if abs(improvement) < spec["min_delta"]:
        return "inconclusive"
    return "effective" if improvement > 0 else "counterproductive"
