"""Test-only JSON-lines transport into the actual county API, with no TCP socket.

This adapter permits a complete browser-state/frontend/backend test in a sandbox
that rejects loopback bind/connect. It does not serve users or fabricate evidence.
"""

import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

# Resolve only the isolated imported package, keeping the original workspace intact.
ROOT = Path(__file__).resolve().parents[2] / "backend/dataclocator"
sys.path.insert(0, str(ROOT / "src"))
from dataclocator.api import create_app


def main():
    """Translate serial HTTP requests into actual ASGI responses for the Node test."""
    protocol = sys.stdout
    # Background model logs belong on stderr, never inside the JSON-lines protocol.
    sys.stdout = sys.stderr
    # The test may provide a fresh owned data root so no completed cache masks worker execution.
    model_root = Path(os.environ.get("DATACLOCATOR_TEST_ROOT", ROOT))
    with TestClient(create_app(model_root)) as client:
        protocol.write(json.dumps({"ready": True}) + "\n")
        protocol.flush()
        for line in sys.stdin:
            request = json.loads(line)
            if request.get("close"):
                break
            response = client.request(request["method"], request["path"], content=request.get("body"),
                                      headers={"Content-Type": "application/json"})
            protocol.write(json.dumps({"status": response.status_code, "body": response.json()}, allow_nan=False) + "\n")
            protocol.flush()


if __name__ == "__main__":
    # This script runs only under the opt-in real-data integration test.
    main()
