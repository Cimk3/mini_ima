#include "miniima/exact_index.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <queue>
#include <stdexcept>
#include <unordered_set>
#include <utility>

namespace miniima {
namespace {

struct Better {
    bool operator()(const SearchResult& left, const SearchResult& right) const {
        return left.score > right.score || (left.score == right.score && left.id < right.id);
    }
};

}  // namespace

ExactIndex::ExactIndex(std::size_t dimension) : dimension_(dimension) {
    if (dimension == 0) {
        throw std::invalid_argument("dimension must be positive");
    }
}

std::vector<float> ExactIndex::normalize(std::span<const float> vectors) const {
    if (vectors.size() % dimension_ != 0) {
        throw std::invalid_argument("vector dimension mismatch");
    }
    std::vector<float> result(vectors.size());
    for (std::size_t start = 0; start < vectors.size(); start += dimension_) {
        double squared_norm = 0;
        for (std::size_t column = 0; column < dimension_; ++column) {
            const double value = vectors[start + column];
            if (!std::isfinite(value)) {
                throw std::invalid_argument("vectors contain NaN or Inf");
            }
            squared_norm += value * value;
        }
        if (squared_norm == 0 || !std::isfinite(squared_norm)) {
            throw std::invalid_argument("zero vector or invalid norm");
        }
        const double norm = std::sqrt(squared_norm);
        for (std::size_t column = 0; column < dimension_; ++column) {
            result[start + column] = static_cast<float>(vectors[start + column] / norm);
        }
    }
    return result;
}

void ExactIndex::add(std::span<const ChunkId> ids, std::span<const float> vectors) {
    if (ids.size() > std::numeric_limits<std::size_t>::max() / dimension_
        || vectors.size() != ids.size() * dimension_) {
        throw std::invalid_argument("id count or vector dimension mismatch");
    }
    std::unordered_set<ChunkId> seen(ids_.begin(), ids_.end());
    for (const auto id : ids) {
        if (id <= 0 || !seen.insert(id).second) {
            throw std::invalid_argument("chunk ids must be positive and unique");
        }
    }
    auto normalized = normalize(vectors);
    if (ids.size() > ids_.max_size() - ids_.size()
        || normalized.size() > vectors_.max_size() - vectors_.size()) {
        throw std::length_error("index is too large");
    }
    // Reserve both containers before changing either logical size.
    ids_.reserve(ids_.size() + ids.size());
    vectors_.reserve(vectors_.size() + normalized.size());
    ids_.insert(ids_.end(), ids.begin(), ids.end());
    vectors_.insert(vectors_.end(), normalized.begin(), normalized.end());
}

void ExactIndex::rebuild(std::span<const ChunkId> ids, std::span<const float> vectors) {
    ExactIndex replacement(dimension_);
    replacement.add(ids, vectors);
    ids_.swap(replacement.ids_);
    vectors_.swap(replacement.vectors_);
}

std::vector<SearchResult> ExactIndex::search(std::span<const float> query, std::size_t k) const {
    if (query.size() != dimension_) {
        throw std::invalid_argument("query dimension mismatch");
    }
    auto normalized = normalize(query);
    k = std::min(k, ids_.size());
    if (k == 0) {
        return {};
    }
    // Better as comparator keeps the worst retained item at the heap root.
    std::priority_queue<SearchResult, std::vector<SearchResult>, Better> heap;
    for (std::size_t row = 0; row < ids_.size(); ++row) {
        double score = 0;
        for (std::size_t column = 0; column < dimension_; ++column) {
            score += static_cast<double>(vectors_[row * dimension_ + column]) * normalized[column];
        }
        SearchResult candidate{ids_[row], std::clamp(score, -1.0, 1.0)};
        if (heap.size() < k) {
            heap.push(candidate);
        } else if (Better{}(candidate, heap.top())) {
            heap.pop();
            heap.push(candidate);
        }
    }
    std::vector<SearchResult> result;
    result.reserve(k);
    while (!heap.empty()) {
        result.push_back(heap.top());
        heap.pop();
    }
    std::sort(result.begin(), result.end(), Better{});
    return result;
}

void ExactIndex::clear() noexcept {
    ids_.clear();
    vectors_.clear();
}

}  // namespace miniima
