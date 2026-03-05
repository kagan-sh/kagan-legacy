import os
import sys

from kagan.runtime_env import strip_noisy_environment_variables


def sanitize_startup_environment() -> tuple[str, ...]:
    return strip_noisy_environment_variables(os.environ, platform_name=sys.platform)


__all__ = ["sanitize_startup_environment"]
