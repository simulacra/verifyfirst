"""verifyfirst — an MCP server for what your verification method cannot see.

https://verifyfirst.dev
"""
import sys

from . import server

__version__ = "1.3.0"
__all__ = ["cli", "server"]


def cli() -> int:
    """Console-script entry point. The module keeps taking argv explicitly so
    it stays runnable as a bare script for anyone who clones the repo."""
    return server.main(sys.argv[1:])
