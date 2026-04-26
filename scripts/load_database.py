from src.load.loader import load_jsonl_to_database, create_tables


def main():
    create_tables()
    load_jsonl_to_database()

if __name__ == "__main__":
    main()