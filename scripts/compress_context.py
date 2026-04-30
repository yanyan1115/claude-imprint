#!/usr/bin/env python3
"""
Compress recent_context.md when it grows too large.
Thin wrapper so the post-response hook doesn't need to know implementation details.

Usage:
  python3 scripts/compress_context.py <context-file-path>

If memo_clover.compress is available, delegates to compress_file().
Otherwise falls back to simple tail truncation (keep last 60 lines).
"""

import sys
from pathlib import Path


def compress_simple(filepath: Path, keep_lines: int = 60):
    """Fallback: keep only the last N lines."""
    lines = filepath.read_text(encoding="utf-8").splitlines()
    if len(lines) <= keep_lines:
        return  # nothing to compress
    trimmed = lines[-keep_lines:]
    filepath.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
    print(f"Compressed {len(lines)} -> {len(trimmed)} lines (simple tail)")


def main():
    if len(sys.argv) < 2:
        print("Usage: compress_context.py <context-file>", file=sys.stderr)
        sys.exit(1)

    filepath = Path(sys.argv[1])
    if not filepath.exists():
        print(f"File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    try:
        from memo_clover.compress import compress_file
    except ImportError:
        # Package not available; keep hooks functional with local truncation.
        compress_simple(filepath)
        return

    compress_file(filepath)
    print("Compressed via memo_clover.compress")


if __name__ == "__main__":
    main()
