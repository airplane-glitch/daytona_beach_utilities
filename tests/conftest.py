"""Loads the integration's pure modules without needing Home Assistant installed."""
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "daytona_beach_utilities"

if "dbu" not in sys.modules:
    pkg = types.ModuleType("dbu")
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules["dbu"] = pkg
