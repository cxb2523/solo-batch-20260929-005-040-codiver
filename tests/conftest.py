import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# java_analyzer modules import each other as top-level packages
# (``detectors``, ``utils``), so its directory must come first on sys.path.
sys.path.insert(0, str(ROOT / "src" / "java_analyzer"))
sys.path.insert(1, str(ROOT / "src"))
