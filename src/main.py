"""Entry point for the AHK Macro Builder application."""

import sys
import os

# Ensure the project root is on the path so 'src' imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.app import AHKMacroBuilderApp


def main():
    app = AHKMacroBuilderApp()
    app.run()


if __name__ == "__main__":
    main()
