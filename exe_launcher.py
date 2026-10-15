"""Entry point for the Windows EXE (built with build_exe.bat).

Starts the Streamlit app from inside the bundle, on this computer only, and opens it in the browser.
"""
import os
import sys

import whatsapp_analyzer  # noqa: F401  (makes PyInstaller bundle everything the app imports)
from streamlit.web import cli as stcli


def main():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    print("Starting Chat Analyzer. Your browser will open in a moment.")
    print("Keep this window open while you use it. Close it to stop the app.\n")
    sys.argv = [
        "streamlit", "run", os.path.join(base, "whatsapp_analyzer.py"),
        "--global.developmentMode=false",
        "--server.address=localhost",          # only this computer can open the app
        "--server.headless=false",             # open the browser automatically
        "--browser.gatherUsageStats=false",    # no usage statistics
        "--client.toolbarMode=minimal",        # no "Deploy" button
        "--logger.hideWelcomeMessage=true",    # no Streamlit promo messages or pop-ups
        "--theme.base=dark",
        "--theme.primaryColor=#53BDEB",
        "--theme.backgroundColor=#0B1A1E",
        "--theme.secondaryBackgroundColor=#12262B",
        "--theme.textColor=#E7EEEC",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
