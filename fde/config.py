"""Locations, all overridable by environment. Nothing in the harness hardcodes an absolute path.
FDE_HOME   workspace root (contains fde/ and runs/). Default: the folder above this file.
FDE_RUNS   where run directories and PREREG files live.        Default: $FDE_HOME/runs
FDE_VAULT  the Obsidian vault used for persistence.            Default: ~/Documents/Vault"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
HOME_DIR = os.environ.get("FDE_HOME") or os.path.dirname(HERE)
RUNS = os.environ.get("FDE_RUNS") or os.path.join(HOME_DIR, "runs")
VAULT = os.path.expanduser(os.environ.get("FDE_VAULT") or "~/Documents/Vault")
EXP_DIR = os.path.join(VAULT, "50_Experiments", "FDE-Kernel")       # generated run notes + world reports
LESSONS_DIR = os.path.join(VAULT, "40_Memory", "FDE-Lessons")        # lessons, gap records, regression tests (cross-mission memory)
