import os
import sys
import tempfile
from pathlib import Path

# Deterministic, network-free test runs (demo/fallback mode, shorter history)
os.environ["ENERPILOT_OFFLINE"] = "1"
os.environ["ENERPILOT_HISTORY_DAYS"] = "60"
os.environ["ENERPILOT_WARM_CACHE"] = "0"
os.environ["ENERPILOT_DATA_DIR"] = tempfile.mkdtemp(prefix="enerpilot_test_")
os.environ["ENERPILOT_FRONTEND_DIST"] = str(Path(tempfile.gettempdir()) / "enerpilot_no_dist")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
