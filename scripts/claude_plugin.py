#!/usr/bin/env python3
"""Claude Code plugin launcher: runs the hooks and the MCP server from the plugin's own copy of the ekbasis package
(no install, no network). See ekbasis/claude_plugin.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.version_info < (3, 9):
    sys.exit(f"ekbasis plugin: needs Python 3.9 or later on PATH as python3 (found {sys.version.split()[0]})")

from ekbasis.claude_plugin import main  # noqa: E402

sys.exit(main())
