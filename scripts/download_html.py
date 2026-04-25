from config import START_DATE, END_DATE
from src.extract.downloader import run_download


def main():
    run_download(START_DATE, END_DATE)


if __name__ == "__main__":
    main()