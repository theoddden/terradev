#!/usr/bin/env python3
"""
Terradev CLI Module Entry Point
"""

import sys


def main():
    """Main entry point"""
    try:
        from .cli import cli
        cli()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
