"""Vendored mistune 3.1.4 (https://github.com/lepture/mistune, BSD-3-Clause).

This file replaces upstream's ``__init__.py``. The original builds convenience
instances at import time via ``create_markdown(plugins=["table", ...])``, and
that plugin loader resolves names through ``import_module("mistune.plugins.*")``
-- an absolute path that does not exist when the package is vendored under
another name, so merely importing it raised ModuleNotFoundError.

Nothing else is modified. ``vellum.parse`` imports the submodules directly and
passes plugin functions rather than names, so none of the upstream conveniences
are needed. To update mistune, copy in the new ``src/mistune`` and restore this
file.
"""

__version__ = "3.1.4"
__all__ = []
