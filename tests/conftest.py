"""
conftest.py — Add the project root to sys.path so pytest can import app, config, etc.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
