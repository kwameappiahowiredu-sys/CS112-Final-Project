import runpy
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "data" / "raw"

import task1_1_cleaning
import task1_2_eda
import task1_3_integration

def banner(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)
    
def main():
    required = ["utilities.csv", "substations.csv", "lines.csv"]
    if not all((RAW / name).exists() for name in required):
        banner("Generating synthetic datasets")
        runpy.run_path(str(BASE / "generate_datasets.py"), run_name="__main__")
    banner("Task 1.1 Data Cleaning and Preprocessing")
    task1_1_cleaning.main()
    banner("Task 1.2 Exploratory Data Analysis")
    task1_2_eda.main()
    banner("Task 1.3 Data Integration and Relationship Mapping")
    task1_3_integration.main()
    banner("Week 1 complete")
    print("Clean data:      data/clean")
    print("Lookups:         data/lookups")
    print("Figures:         figures")
    print("Reports:         reports")
    return 0

if __name__ == "__main__":
    sys.exit(main())
