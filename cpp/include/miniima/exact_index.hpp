#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace miniima {

using ChunkId = std::int64_t;

struct SearchResult {
    ChunkId id;
    double score;
};

// Exact cosine search with contiguous float32 storage and deterministic ties.
class ExactIndex {
public:
    explicit ExactIndex(std::size_t dimension);
    void add(std::span<const ChunkId> ids, std::span<const float> vectors);
    void rebuild(std::span<const ChunkId> ids, std::span<const float> vectors);
    std::vector<SearchResult> search(std::span<const float> query, std::size_t k) const;
    void clear() noexcept;
    std::size_t size() const noexcept { return ids_.size(); }
    std::size_t dimension() const noexcept { return dimension_; }

private:
    std::vector<float> normalize(std::span<const float> vectors) const;
    std::size_t dimension_;
    std::vector<ChunkId> ids_;
    std::vector<float> vectors_;
};

}  // namespace miniima
