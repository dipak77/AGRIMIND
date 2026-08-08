"""Allow ``python -m agrimind_kernel.feedback`` as alias for migrate."""

from agrimind_kernel.feedback.migrate import main

if __name__ == "__main__":
    raise SystemExit(main())
