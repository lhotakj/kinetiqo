"""Module entrypoint used by `python -m kinetiqo`.

This module simply delegates to :func:`kinetiqo.cli.cli` so that the package
is runnable with ``python -m kinetiqo``.  Keeping the module lightweight
avoids side-effects at import time.
"""

from kinetiqo.cli import cli


if __name__ == "__main__":
    cli()
