"""SDK logger.

Library policy: emit through the standard ``logging`` module under the
``retrace`` namespace and attach a ``NullHandler`` so the SDK is silent
by default. Applications configure verbosity with
``logging.getLogger("retrace").setLevel(...)``.
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "retrace"

logger = logging.getLogger(_LOGGER_NAME)
logger.addHandler(logging.NullHandler())


def get_logger() -> logging.Logger:
    return logger
