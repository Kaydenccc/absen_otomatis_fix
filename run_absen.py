#!/usr/bin/env python3
# run_absen.py - File khusus untuk PythonAnywhere scheduled task

import sys
import os

# Tambahkan path current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from absen_cloud import main

if __name__ == "__main__":
    main()