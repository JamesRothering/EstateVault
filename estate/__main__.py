"""Estate Continuity Layer — health from Firefly, never a second ledger."""

from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    import os

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    _load_env_file(Path(__file__).resolve().parent.parent / ".env")
    from estate.app import main as serve

    serve()


if __name__ == "__main__":
    main()
