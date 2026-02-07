import sys
from evolution.init import init_repo


def main():
    if len(sys.argv) < 2:
        print("Usage: evolution init")
        return

    command = sys.argv[1]

    if command == "init":
        init_repo()
    elif command == "ingest":
        from evolution.ingest import ingest_repo
        ingest_repo()
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
