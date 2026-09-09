from dotenv import load_dotenv
load_dotenv()

import onnxruntime  # noqa: E402,F401  # import-order guard — must precede any dspy import; see module.py


def main() -> None:
    print("Hello from factextract!")
