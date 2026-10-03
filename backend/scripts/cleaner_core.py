"""
cleaner_core.py - Shim importing from app.services.data_cleaner or standalone.
"""
import sys
from pathlib import Path

# Add backend directory to sys.path if not present
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.data_cleaner import *
