"""Path setup for HEMS Lite tests."""

import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(_root, "services", "sentinel", "src"))
sys.path.insert(0, os.path.join(_root, "services", "_common"))
