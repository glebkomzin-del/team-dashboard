"""Entrypoint for the same checker that is copied into /app."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parent/'overlay/offline_check.py'),run_name='__main__')
