"""Executable entry point for the ``findata`` package.

Run with::

    python -m findata
"""

from findata.db.session import main


if __name__ == "__main__":
    main()