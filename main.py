"""Launch the factextract Streamlit GUI.

Usage:
    python main.py
    python main.py --server.port 8502        # extra args are forwarded to `streamlit run`
    python main.py --server.headless true    # e.g. skip first-run email prompt / browser open
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
GUI = SRC / "factextract" / "facts_viewer.py"

# Make the package importable even when it is NOT pip-installed (bare
# `python main.py`). With uv or `pip install -e .` this is a no-op —
# and because the Streamlit server runs in this same process, the
# sys.path insert also covers facts_viewer.py's absolute imports.
try:
    import factextract  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(SRC))
    import factextract  # noqa: F401

from streamlit.web import cli as stcli  # noqa: E402


def main() -> None:
    if not GUI.exists():
        sys.exit(f"GUI script not found: {GUI}")

    # Re-exec as: streamlit run src/factextract/facts_viewer.py [extra args]
    sys.argv = ["streamlit", "run", str(GUI), *sys.argv[1:]]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
