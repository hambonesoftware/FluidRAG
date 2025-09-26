from fluidrag.backend.core.chunking.microchunker import iter_microchunks


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
