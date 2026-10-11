"""Schema and reference checks for the Power BI project (exit code 1 on any problem). Run from powerbi/."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbikit import validate  # noqa: E402

sys.exit(1 if validate(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) else 0)
