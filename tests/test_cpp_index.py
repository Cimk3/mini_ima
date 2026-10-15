from dataclasses import replace

import numpy as np
import pytest

from miniima._exact import ExactIndex
from miniima.application.service import KnowledgeService
from miniima.vector.numpy_index import ExactIndex as NumpyIndex


@pytest.mark.parametrize("dimension,count,k", [(2, 0, 5), (8, 1, 10), (32, 200, 5), (768, 1000, 20)])
def test_cpp_matches_numpy_with_fixed_seed(dimension, count, k):
    rng = np.random.default_rng(42)
    vectors = rng.standard_normal((count, dimension)).astype(np.float32)
    ids = rng.permutation(np.arange(1, count + 1, dtype=np.int64))
    cpp, reference = ExactIndex(dimension), NumpyIndex(dimension)
    cpp.rebuild(ids, vectors)
    reference.rebuild(ids, vectors)
    for _ in range(10):
        query = rng.standard_normal(dimension).astype(np.float32)
        actual, expected = cpp.search(query, k), reference.search(query, k)
        assert [item[0] for item in actual] == [item[0] for item in expected]
        np.testing.assert_allclose([item[1] for item in actual], [item[1] for item in expected], rtol=1e-6, atol=1e-7)


def test_heap_tie_cutoff_and_noncontiguous_input():
    index = ExactIndex(2)
    matrix = np.tile([1., 0., 9., 9.], (5, 1))[:, :2]
    assert not matrix.flags.c_contiguous
    index.add([9, 7, 3, 1, 5], matrix)
    assert [item[0] for item in index.search([2., 0.], 3)] == [1, 3, 5]
    index.clear()
    assert index.size() == 0


@pytest.mark.parametrize("ids,vectors", [([1], [[0., 0.]]), ([1], [[float("nan"), 1.]]),
    ([1], [[1., float("inf")]]), ([1], [[1., 2., 3.]]), ([1, 1], [[1., 0.], [0., 1.]]),
    ([0], [[1., 0.]]), ([-1], [[1., 0.]]), ([1.5], [[1., 0.]]), ([True], [[1., 0.]]),
    ([2**70], [[1., 0.]]), ([1, 2], [[1., 0.]])])
def test_invalid_rebuild_preserves_index(ids, vectors):
    index = ExactIndex(2)
    index.add([20], [[1., 0.]])
    with pytest.raises((ValueError, TypeError)):
        index.rebuild(ids, vectors)
    assert index.size() == 1 and index.search([1., 0.], 1)[0][0] == 20


@pytest.mark.parametrize("query,k", [([0., 0.], 1), ([1.], 1), ([float("nan"), 0.], 1),
                                    ([1., 0.], -1), ([[1., 0.]], 1)])
def test_invalid_queries_even_on_empty_index(query, k):
    with pytest.raises(ValueError):
        ExactIndex(2).search(query, k)


def test_cpp_application_rebuilds_from_database(tmp_path, repository, settings, provider):
    settings = replace(settings, retrieval_engine="cpp")
    kb = repository.create_kb("cpp", settings)
    path = tmp_path / "a.md"
    path.write_text("# TCP\n\nTCP 三次握手。", encoding="utf-8")
    service = KnowledgeService(repository, settings, provider)
    service.add(path, kb["id"])
    assert service.search("TCP", kb["id"])[0]["filename"] == "a.md"
    assert service.ask("TCP", kb["id"]).citations[0]["filename"] == "a.md"
