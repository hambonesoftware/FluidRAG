from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chunking.atomic_chunker import AtomicChunker


def test_atomic_chunker_splits_bullets_and_copies_leadin():
    chunker = AtomicChunker()
    pages = [
        {
            "page": 1,
            "text": (
                "5.3.1 Emergency stop\n"
                "The control system shall provide the following:\n"
                "(a) a red mushroom stop button located near the operator;\n"
                "(b) a second stop station for maintenance personnel."
            ),
        }
    ]
    chunks = chunker.chunk("ISO_10218-1:2011", pages, [])
    texts = [chunk["text"] for chunk in chunks]
    assert any("red mushroom" in text for text in texts)
    assert any("second stop" in text for text in texts)
    prefixes = [chunk["prefix"] for chunk in chunks]
    assert all(prefix.startswith("ISO_10218-1:2011 §5.3.1") for prefix in prefixes)
    assert any("shall provide the following" in prefix for prefix in prefixes)


def test_atomic_chunker_splits_semicolons():
    chunker = AtomicChunker()
    pages = [
        {
            "page": 2,
            "text": (
                "6.2 Guarding requirements\n"
                "The machine shall include perimeter guarding; it shall also interlock access gates."
            ),
        }
    ]
    chunks = chunker.chunk("ISO_10218-1:2011", pages, [])
    assert len(chunks) == 2
    assert "perimeter guarding" in chunks[0]["text"]
    assert "interlock access gates" in chunks[1]["text"]
