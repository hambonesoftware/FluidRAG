from fluidrag.backend.core.chunking.microchunker import chunk, iter_microchunks


def test_microchunk_window_and_stride():
    sentence = "The system shall start within five seconds. "
    text = sentence * 40
    windows = list(iter_microchunks(text, window_chars=300, stride_chars=100))
    assert windows
    lengths = [end - start for start, end, _ in windows]
    for length in lengths[:-1]:
        assert 270 <= length <= 330
    for (start_a, _, _), (start_b, _, _) in zip(windows, windows[1:]):
        stride = start_b - start_a
        assert 80 <= stride <= 140


def test_microchunk_prefers_sentence_boundaries():
    text = "The valve shall close. The pump shall stop. The alarm shall sound."
    windows = list(iter_microchunks(text, window_chars=60, stride_chars=20))
    assert all(window_text.endswith(".") for _, _, window_text in windows)


def test_chunk_emits_signals():
    text = (
        "The system shall maintain 95% uptime. "
        "Each robot must provide diagnostics. "
        "Temperature shall stay ≤ 40 °C."
    )
    windows = list(chunk(text, window_chars=80, stride_chars=40))
    assert windows
    for window in windows:
        assert 0.0 <= window.E <= 1.0
        assert 0.0 <= window.F <= 1.0
        assert 0.0 <= window.H <= 1.0
