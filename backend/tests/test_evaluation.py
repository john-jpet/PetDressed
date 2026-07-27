import numpy as np

from scripts.evaluate_cv import intersection_over_union


def test_intersection_over_union_handles_overlap_and_empty_masks():
    expected = np.array([[1, 1], [0, 0]], dtype=bool)
    predicted = np.array([[1, 0], [1, 0]], dtype=bool)
    assert intersection_over_union(predicted, expected) == 1 / 3
    empty = np.zeros((2, 2), dtype=bool)
    assert intersection_over_union(empty, empty) == 1
