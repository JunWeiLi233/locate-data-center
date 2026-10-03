"""Verify the frontend did not alter the accepted model executable or baseline configs."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
freeze = json.loads((root / "runs/phase7/executable_freeze_v2.json").read_text(encoding="utf-8"))
result = {"checked": {}, "mismatches": []}
for group in ("code_hashes", "config_hashes"):
    values = freeze[group]
    for relative, expected in values.items():
        path = root / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual != expected:
            result["mismatches"].append({"path": relative, "expected": expected, "actual": actual})
    result["checked"][group] = len(values)
result["accepted_phase7_sha256"] = hashlib.sha256((root / "docs/phase_records/phase_7.json").read_bytes()).hexdigest()
result["accepted_phase7_unchanged"] = result["accepted_phase7_sha256"] == "29d0fc1aa4ab807fd6263a011a69207377290930cc77e32452e1a9ab878bc16f"
out = root / "frontend/output/backend-preservation.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
raise SystemExit(bool(result["mismatches"]) or not result["accepted_phase7_unchanged"])
