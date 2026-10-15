import numpy as np
import pytest

from miniima.vector.numpy_index import ExactIndex


def test_numpy_top_k_ties_add_clear_and_empty():
    index = ExactIndex(2)
    assert index.search([1, 0], 5) == []
    index.add([9, 2, 5], [[1, 0], [2, 0], [0, 1]])
    assert [item[0] for item in index.search([1, 0], 10)] == [2, 9, 5]
    assert index.search([1, 0], 0) == []
    with pytest.raises(ValueError):
        index.add([2], [[1, 1]])
    assert index.size() == 3
    index.clear()
    assert index.size() == 0


@pytest.mark.parametrize("bad", [[[0., 0.]], [[float("nan"), 1.]], [[1., float("inf")]], [[1., 2., 3.]]])
def test_numpy_invalid_rebuild_is_atomic(bad):
    index = ExactIndex(2)
    index.add([1], [[1., 0.]])
    with pytest.raises(ValueError):
        index.rebuild([2], bad)
    assert index.size() == 1 and index.search([1, 0], 1)[0][0] == 1
