import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.load.loader import load_jsonl_to_database, create_tables


def main():
    create_tables()
    load_jsonl_to_database()

if __name__ == "__main__":
    main()