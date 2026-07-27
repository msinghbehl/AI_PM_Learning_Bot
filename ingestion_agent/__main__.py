"""Entry point for `python -m ingestion_agent`."""
import sys

from ingestion_agent.cli import main

if __name__ == "__main__":
    sys.exit(main())
