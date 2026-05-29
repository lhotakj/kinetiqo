"""Top-level package for Kinetiqo.

This package contains the core application modules used by the CLI and web
frontend.  The package-level docstring documents the project at import time
and is intentionally minimal — functionality is provided by submodules such
as :mod:`kinetiqo.cli`, :mod:`kinetiqo.sync` and :mod:`kinetiqo.web`.

Do not perform heavy initialization at import time so unit tests can import
submodules without side-effects.
"""

__all__ = [
	"cli",
	"sync",
	"strava",
	"db",
	"web",
]

