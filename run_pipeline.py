"""
One-command build.

    python run_pipeline.py --fetch      # 1st time: call the APIs (OneMap ~1 h), then build
    python run_pipeline.py              # rebuild from cached downloads (minutes)
    python run_pipeline.py --offline    # only steps that need no API data (tables, keys, QA)
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))

FETCH = [["fetch_datagov.py"], ["fetch_onemap.py", "mrt"], ["fetch_onemap.py", "hdb"], ["fetch_ura_private.py"]]
PREP = [["prep_supply.py"], ["prep_population.py"], ["prep_hdb.py"], ["prep_mrt.py"]]
SPATIAL = [["build_demand.py"], ["compute_access.py"]]
MODEL = [["build_model.py"]]


def run(step):
    t = time.time()
    print(f"\n=== {' '.join(step)} ===", flush=True)
    r = subprocess.run([sys.executable, str(SRC / step[0]), *step[1:]], cwd=SRC)
    print(f"--- {step[0]} finished in {time.time()-t:.0f}s (exit {r.returncode})")
    return r.returncode


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="call external APIs first")
    ap.add_argument("--offline", action="store_true", help="skip spatial steps")
    a = ap.parse_args()
    steps = (FETCH if a.fetch else []) + PREP + ([] if a.offline else SPATIAL) + MODEL
    for s in steps:
        code = run(s)
        if code and s[0] != "fetch_ura_private.py":
            # URA is optional (land-use fallback exists); everything else must succeed
            sys.exit(f"\nStopped at {' '.join(s)}. Fix the message above and re-run - "
                     "finished downloads/geocodes are cached and will be skipped.")
