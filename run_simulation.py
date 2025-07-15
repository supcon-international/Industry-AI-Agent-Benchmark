#!/usr/bin/env python3
"""
Launcher script for the SUPCON Factory Simulation.
This script properly sets up the Python path and runs the main simulation.
"""

import sys
import os

# Add the project root to Python path so that 'src' and 'config' can be imported
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Now we can import and run the main simulation
if __name__ == "__main__":
    from src.main import main
    # Pass all command-line arguments to the main function
    sys.exit(main(sys.argv[1:])) 