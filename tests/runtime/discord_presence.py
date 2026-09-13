"""Exercise Petros against local Discord desktop, without Arma or server config."""

import argparse
import importlib.util
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application_id", nargs="?", default=os.environ.get("RICH_PRESENCE_APPLICATION_ID", ""))
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error("--seconds must be positive")

    path = Path(__file__).resolve().parents[2] / "python_code" / "__init__.py"
    spec = importlib.util.spec_from_file_location("petros_presence", path)
    petros = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(petros)
    if not petros.update_presence(args.application_id, "Petros Rich Presence Test", "Local IPC Test"):
        parser.error("pass a valid Discord Application ID or set RICH_PRESENCE_APPLICATION_ID")
    print("Queued; look for 'Discord activity accepted' and inspect Discord desktop. Ctrl+C to clear.", flush=True)
    accepted = False
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            accepted = accepted or petros._presence_last_activity is not None
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        petros.clear_presence()
        # Give the asynchronous clear its IPC deadline before process exit closes handles.
        time.sleep(2.1)
    if not accepted:
        print("No activity acknowledgement observed; see the IPC diagnostics above.", flush=True)
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
