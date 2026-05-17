from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
ACTIVE_ROS_FILE = STATE_DIR / "active_ros.json"
SHOP_STATE_FILE = STATE_DIR / "shop_state.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_active_ros_state import build_active_ros_state
from scripts.build_shop_state import build_shop_state


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    active_ro_state = build_active_ros_state()
    ACTIVE_ROS_FILE.write_text(json.dumps(active_ro_state, indent=2), encoding="utf-8")

    shop_state = build_shop_state()
    SHOP_STATE_FILE.write_text(json.dumps(shop_state, indent=2), encoding="utf-8")

    print(ACTIVE_ROS_FILE)
    print(f"Active ROs: {active_ro_state['count']}")
    print(SHOP_STATE_FILE)
    print(f"Jobs: {shop_state['count']}")


if __name__ == "__main__":
    main()
