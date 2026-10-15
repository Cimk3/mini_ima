#include "miniima/exact_index.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

void check(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

template <typename Callable>
void invalid(Callable callable) {
    try {
        callable();
    } catch (const std::invalid_argument&) {
        return;
    }
    throw std::runtime_error("expected invalid_argument");
}

int main() {
    using miniima::ChunkId;
    try {
        invalid([] { miniima::ExactIndex zero(0); });
        miniima::ExactIndex index(2);
        const std::vector<float> query{1, 0};
        check(index.search(query, 5).empty(), "empty index");
        index.add(std::vector<ChunkId>{9, 2, 5}, std::vector<float>{1, 0, 2, 0, 0, 1});
        auto results = index.search(query, 10);
        check(results.size() == 3 && results[0].id == 2 && results[1].id == 9 && results[2].id == 5,
              "stable ties and k > size");
        check(std::abs(results[0].score - 1) < 1e-6, "cosine normalization");
        check(index.search(query, 0).empty(), "zero k");
        invalid([&] { index.add(std::vector<ChunkId>{2}, std::vector<float>{1, 1}); });
        invalid([&] { index.rebuild(std::vector<ChunkId>{3}, std::vector<float>{0, 0}); });
        invalid([&] { index.rebuild(std::vector<ChunkId>{3}, std::vector<float>{1, 2, 3}); });
        invalid([&] { index.search(std::vector<float>{1}, 1); });
        invalid([&] { index.search(std::vector<float>{0, 0}, 1); });
        invalid([&] { index.add(std::vector<ChunkId>{3}, std::vector<float>{NAN, 1}); });
        invalid([&] { index.add(std::vector<ChunkId>{3}, std::vector<float>{INFINITY, 1}); });
        invalid([&] { index.add(std::vector<ChunkId>{-1}, std::vector<float>{1, 0}); });
        check(index.size() == 3, "invalid mutations must be atomic");
        index.rebuild(std::vector<ChunkId>{100}, std::vector<float>{-1, 0});
        check(index.size() == 1 && index.search(query, 1)[0].score == -1, "rebuild and negative cosine");
        const auto largest = std::numeric_limits<float>::max();
        index.rebuild(std::vector<ChunkId>{1}, std::vector<float>{largest, largest});
        check(std::isfinite(index.search(query, 1)[0].score), "large finite vectors");
        index.clear();
        check(index.size() == 0, "clear");
        std::cout << "ExactIndex edge cases passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
