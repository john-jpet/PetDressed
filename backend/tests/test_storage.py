import uuid
from dataclasses import dataclass

from app.storage import garment_colors_for, presigned_read_url


@dataclass
class FakeColor:
    garment_id: uuid.UUID
    rank: int
    hex_value: str
    lab_l: float
    lab_a: float
    lab_b: float
    proportion: float


class FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    """Records how many queries a caller issues."""

    def __init__(self, rows):
        self._rows = rows
        self.query_count = 0

    def scalars(self, _statement):
        self.query_count += 1
        return FakeScalars(self._rows)


def color(garment_id: uuid.UUID, rank: int, hex_value: str) -> FakeColor:
    return FakeColor(garment_id, rank, hex_value, 50.0, 0.0, 0.0, 1.0 / (rank + 1))


def test_palettes_for_many_garments_use_a_single_query():
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session = FakeSession(
        [
            color(first, 0, "#111111"),
            color(first, 1, "#222222"),
            color(second, 0, "#333333"),
            color(third, 0, "#444444"),
        ]
    )

    palettes = garment_colors_for(session, [first, second, third])

    # The point of the helper: cost stays flat as the page grows.
    assert session.query_count == 1
    assert [entry.hex for entry in palettes[first]] == ["#111111", "#222222"]
    assert [entry.hex for entry in palettes[second]] == ["#333333"]
    assert [entry.hex for entry in palettes[third]] == ["#444444"]


def test_palette_lookup_short_circuits_on_an_empty_page():
    session = FakeSession([])
    assert garment_colors_for(session, []) == {}
    assert session.query_count == 0


def test_garments_without_colors_are_absent_rather_than_missing_keys():
    known, bare = uuid.uuid4(), uuid.uuid4()
    session = FakeSession([color(known, 0, "#555555")])

    palettes = garment_colors_for(session, [known, bare])

    assert bare not in palettes
    # Callers use .get(id, []) so a bare garment still renders.
    assert palettes.get(bare, []) == []


def test_missing_object_key_yields_an_empty_url_rather_than_raising():
    # Artifact keys are nullable while a garment is mid-pipeline.
    assert presigned_read_url(None, object()) == ""
    assert presigned_read_url("", object()) == ""
