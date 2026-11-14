"""`python -m podcast_kg …` is the same entry point as the `podcast-kg` script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
