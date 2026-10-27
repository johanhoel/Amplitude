#!/usr/bin/env python3
"""Home Deck - starts homedeck/ (code) with homedeck.toml (settings). Safe restart after changes: homedeck-apply"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from homedeck.main import run
run()
