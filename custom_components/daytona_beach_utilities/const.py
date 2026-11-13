"""Constants for the Daytona Beach Utilities integration."""
from datetime import timedelta

DOMAIN = "daytona_beach_utilities"
SCAN_INTERVAL = timedelta(hours=6)  # bills change about once a month, so there is no point polling faster
