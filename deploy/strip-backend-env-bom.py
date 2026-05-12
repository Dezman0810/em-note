#!/usr/bin/env python3
"""Убрать UTF-8 BOM и \\r из backend/.env — иначе Docker Compose не подхватывает переменные."""
from pathlib import Path
import sys


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/.env")
    b = path.read_bytes()
    while b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    text = b.decode("utf-8", errors="replace").replace("\ufeff", "")
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
