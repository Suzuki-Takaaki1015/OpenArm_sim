#!/usr/bin/env python3
"""Run the canonical diagnostic module from this checkout."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parents[1] / 'docker/app/oa_doctor.py'), run_name='__main__')
