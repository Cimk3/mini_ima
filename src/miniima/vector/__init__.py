from miniima.errors import MiniimaError


def create_index(dimension: int, engine: str):
    if engine == "numpy":
        from miniima.vector.numpy_index import ExactIndex
        return ExactIndex(dimension)
    if engine == "cpp":
        try:
            from miniima._exact import ExactIndex
        except ImportError as exc:
            raise MiniimaError("C++ 扩展不可用。请重新安装，或显式配置 --engine numpy。") from exc
        return ExactIndex(dimension)
    raise MiniimaError("未知检索引擎。")
