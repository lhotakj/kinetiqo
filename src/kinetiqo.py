#!/usr/bin/env python3
"""Minimal CLI entrypoint for the Kinetiqo application.

This module is installed as a console entrypoint in some deployments and
provides a tiny wrapper that delegates to :mod:`kinetiqo.cli`.

The file intentionally contains no runtime logic beyond calling ``cli()``
so it is safe to import in tests and tooling.
"""

from kinetiqo.cli import cli


if __name__ == "__main__":
    cli()
