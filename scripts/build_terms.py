import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.transform.term_builder import build_missing_terms


def main():
    build_missing_terms()


if __name__ == "__main__":
    main()
