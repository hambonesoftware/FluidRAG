from __future__ import annotations

from fluidrag.src.scoring.features import shannon_entropy, smooth_series


def test_shannon_entropy_bounds():
    tokens = ["a", "b", "c", "d"]
    entropy = shannon_entropy(tokens)
    assert 0.0 <= entropy <= 1.0


def test_smooth_series_monotonic_window():
    values = [0.1, 0.5, 0.2, 0.4]
    smoothed = smooth_series(values, window=3)
    assert len(smoothed) == len(values)
    # Smoothed values should not exceed the max of their window
    for idx, value in enumerate(smoothed):
        window = values[max(0, idx - 2) : idx + 1]
        assert min(window) <= value <= max(window)
