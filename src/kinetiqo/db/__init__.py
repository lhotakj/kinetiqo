"""Database backends package for Kinetiqo.

This package contains repository implementations and the repository
factory used by the application.  The concrete backends are provided in
``postgresql.py``, ``mysql.py`` and ``firebird.py`` and implement the
:class:`~kinetiqo.db.repository.DatabaseRepository` contract.

Keep this initializer minimal to avoid importing heavy DB drivers at
package import time; use :func:`kinetiqo.db.factory.create_repository`
instead to obtain a repository instance.
"""

__all__ = ["factory", "repository", "postgresql", "mysql", "firebird"]

