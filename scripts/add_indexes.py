import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.load.indexes import create_indexes

def main():
    create_indexes()

if __name__ == "__main__":
    main()