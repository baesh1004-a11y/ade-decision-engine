from __future__ import annotations

import sys

from run_daily_scheduler import main


if __name__ == "__main__":
    if "--market" not in sys.argv:
        sys.argv.extend(["--market", "us"])
    main()
