#include "miniima/exact_index.hpp"

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <stdexcept>
#include <vector>

namespace py = pybind11;
using FloatArray = py::array_t<float, py::array::c_style | py::array::forcecast>;

namespace {

std::vector<miniima::ChunkId> read_ids(const py::iterable& input) {
    std::vector<miniima::ChunkId> result;
    for (const auto item : input) {
        // __index__ accepts Python/NumPy integers, and rejects lossy float casts.
        if (PyBool_Check(item.ptr()) || !PyIndex_Check(item.ptr())) {
            throw std::invalid_argument("chunk ids must be positive int64 integers");
        }
        py::object integer = py::reinterpret_steal<py::object>(PyNumber_Index(item.ptr()));
        if (!integer) {
            throw py::error_already_set();
        }
        const auto id = PyLong_AsLongLong(integer.ptr());
        if (PyErr_Occurred()) {
            PyErr_Clear();
            throw std::invalid_argument("chunk id is outside int64 range");
        }
        result.push_back(id);
    }
    return result;
}

void check_matrix(const FloatArray& vectors, const miniima::ExactIndex& index) {
    if (vectors.ndim() != 2 || static_cast<std::size_t>(vectors.shape(1)) != index.dimension()) {
        throw std::invalid_argument("vector dimension mismatch");
    }
}

}  // namespace

PYBIND11_MODULE(_exact, module) {
    module.doc() = "Mini-ima C++20 exact cosine retrieval";
    py::class_<miniima::ExactIndex>(module, "ExactIndex")
        .def(py::init([](py::ssize_t dimension) {
            if (dimension <= 0) {
                throw std::invalid_argument("dimension must be positive");
            }
            return miniima::ExactIndex(static_cast<std::size_t>(dimension));
        }), py::arg("dimension"))
        .def_property_readonly("dimension", &miniima::ExactIndex::dimension)
        .def("size", &miniima::ExactIndex::size)
        .def("clear", &miniima::ExactIndex::clear)
        .def("add", [](miniima::ExactIndex& index, const py::iterable& input_ids, const FloatArray& vectors) {
            check_matrix(vectors, index);
            auto ids = read_ids(input_ids);
            index.add(ids, {vectors.data(), static_cast<std::size_t>(vectors.size())});
        }, py::arg("ids"), py::arg("vectors"))
        .def("rebuild", [](miniima::ExactIndex& index, const py::iterable& input_ids, const FloatArray& vectors) {
            check_matrix(vectors, index);
            auto ids = read_ids(input_ids);
            index.rebuild(ids, {vectors.data(), static_cast<std::size_t>(vectors.size())});
        }, py::arg("ids"), py::arg("vectors"))
        .def("search", [](const miniima::ExactIndex& index, const FloatArray& query, py::ssize_t k) {
            if (query.ndim() != 1 || k < 0) {
                throw std::invalid_argument("query must be 1D and k must be non-negative");
            }
            const auto matches = index.search({query.data(), static_cast<std::size_t>(query.size())},
                                              static_cast<std::size_t>(k));
            std::vector<std::pair<miniima::ChunkId, double>> result;
            result.reserve(matches.size());
            for (const auto& match : matches) {
                result.emplace_back(match.id, match.score);
            }
            return result;
        }, py::arg("query"), py::arg("k"));
}
