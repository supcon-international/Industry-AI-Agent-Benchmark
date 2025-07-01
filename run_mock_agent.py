#!/usr/bin/env python3
"""
Launcher script for the Mock Agent.
This script properly sets up the Python path and runs the mock agent for testing.
"""

import sys
import os

# Add the project root to Python path so that 'src' and 'config' can be imported
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Now we can import and run the mock agent
if __name__ == "__main__":
    from tools.mock_agent import main
    main() 