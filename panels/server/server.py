#!/usr/bin/env python3
"""Home Deck backend. The code is in homedeck/ (one module per area), the settings in homedeck.toml.
Check before restarting:  homedeck-apply   (or: cd /opt/panel-wrapper && python3 -m homedeck.check)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from homedeck.main import run
run()
