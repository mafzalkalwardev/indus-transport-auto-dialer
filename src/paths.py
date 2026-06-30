"""Centralised path constants for INDUS TRANSPORTS LLC Auto Dialer."""
import os

# Project root = parent of src/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHROME_PROFILES_DIR = os.path.join(ROOT, "chrome_profiles")
LOGS_DIR            = os.path.join(ROOT, "logs")
DATA_DIR            = os.path.join(ROOT, "data")

CRM_DB       = os.path.join(LOGS_DIR, "crm.sqlite3")
CALL_LOG_CSV = os.path.join(LOGS_DIR, "call_logs.csv")
CONFIG_FILE  = os.path.join(ROOT, "dialer_config.json")

LOGO_PNG  = os.path.join(ROOT, "indus_transports_logo.jpg")
LOGO_JPEG = os.path.join(ROOT, "indus_transports_logo.jpg")

# Ensure runtime dirs exist
for _d in (CHROME_PROFILES_DIR, LOGS_DIR, DATA_DIR):
    os.makedirs(_d, exist_ok=True)
