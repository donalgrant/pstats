"""Allow ``python -m stats_cli``."""

import sys

from .cli import main

sys.exit(main())
