#!/usr/bin/env python3
"""Run script for Lin-IASL without installation"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run
from lin_iasl.main import main

if __name__ == "__main__":
    main()