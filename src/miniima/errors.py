class MiniimaError(Exception):
    """A user-facing failure with no secrets in its message."""


class ConfigurationError(MiniimaError):
    pass


class ProviderError(MiniimaError):
    pass
