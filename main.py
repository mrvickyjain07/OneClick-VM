"""
main.py — Clean project entry point
Run from the project root:  python main.py
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from ui.app import run

if __name__ == "__main__":
    run()
