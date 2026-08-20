"""Offline restore helper. Never run this against a live attacked host."""
import json
import sys
from pathlib import Path

HELP = """
BedForge restore (plant manager, offline)

1. Take the attacked machine off the network.
2. Stand up a clean host with a new JWT_SECRET and FILE_ENCRYPTION_KEY.
3. Restore MongoDB collections from the backup ZIP JSON files (jobs.json, beams.json, …).
   Do not import password_hash from anywhere except the users export in that ZIP
   (hashes only — never plaintext).
4. Copy the encrypted uploads/ volume from known-good backup media.
5. Start BedForge, sign in as plant manager, revoke every session and device,
   then force password changes.
6. Keep the audit_log collection — it is evidence.

This script only prints the JSON file list from a backup zip path.
"""


def main():
    print(HELP)
    if len(sys.argv) < 2:
        print("Usage: python restore_backup.py /path/to/bedforge-backup.zip")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print("Backup file not found")
        sys.exit(1)
    print(f"Backup present: {path} ({path.stat().st_size} bytes)")
    try:
        import zipfile
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                print(" -", name)
    except Exception as exc:
        print("Could not list zip:", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
