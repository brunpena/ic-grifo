import threading
import uuid
from types import SimpleNamespace

from app.services import highlights
from app.services.highlights import WordGeometry


def test_indexed_boxes_preserve_lines_pages_and_overlapping_offsets():
    words = [
        WordGeometry(0, 8, 1, 10, 10, 20, 20),
        WordGeometry(0, 8, 1, 21, 10, 30, 20),
        WordGeometry(9, 12, 1, 31, 10, 40, 20),
        WordGeometry(13, 20, 1, 10, 30, 20, 40),
        WordGeometry(21, 25, 2, 10, 10, 20, 20),
    ]
    first, second, empty = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    result = highlights._build_boxes(
        words, {1: (100, 100), 2: (200, 100)},
        {first: (0, 12), second: (8, 25), empty: (25, 30)},
    )
    assert result[first] == [{"page": 1, "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.1}]
    assert result[second] == [
        {"page": 1, "x": 0.31, "y": 0.1, "width": 0.09, "height": 0.1},
        {"page": 1, "x": 0.1, "y": 0.3, "width": 0.1, "height": 0.1},
        {"page": 2, "x": 0.05, "y": 0.1, "width": 0.05, "height": 0.1},
    ]
    assert not result.get(empty)


def test_index_handles_nested_intervals():
    words = [WordGeometry(0, 100, 1, 0, 0, 10, 10), WordGeometry(5, 8, 1, 20, 0, 30, 10)]
    rule = uuid.uuid4()
    boxes = highlights._build_boxes(words, {1: (100, 100)}, {rule: (50, 60)})
    assert boxes[rule] == [{"page": 1, "x": 0, "y": 0, "width": 0.1, "height": 0.1}]


def test_many_rules_only_visit_words_in_their_ranges(monkeypatch):
    reads = 0

    class CountedWord(WordGeometry):
        @property
        def char_end(self):
            nonlocal reads
            reads += 1
            return self[1]

    words = [WordGeometry(i * 10, i * 10 + 5, 1, 0, 0, 10, 10) for i in range(2000)]
    ranges = {uuid.uuid4(): (i * 20, i * 20 + 5) for i in range(500)}
    monkeypatch.setattr(highlights, "WordGeometry", CountedWord)
    result = highlights._build_boxes(words, {1: (100, 100)}, ranges)
    assert len(result) == 500
    # One index pass plus one matching word per rule, not 2000 * 500 checks.
    assert reads <= len(words) + len(ranges)


async def test_box_calculation_runs_outside_event_loop(monkeypatch):
    event_loop_thread = threading.get_ident()
    rule = uuid.uuid4()

    class Database:
        async def scalars(self, _query):
            return [SimpleNamespace(page_number=1, width=100, height=100)]

        async def execute(self, _query):
            return SimpleNamespace(all=lambda: [WordGeometry(0, 5, 1, 0, 0, 10, 10)])

    original = highlights._build_boxes

    def calculate(*args):
        assert threading.get_ident() != event_loop_thread
        return original(*args)

    monkeypatch.setattr(highlights, "_build_boxes", calculate)
    result = await highlights.rule_boxes(Database(), uuid.uuid4(), {rule: (0, 5)})
    assert len(result[rule]) == 1
