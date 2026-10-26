import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.ai import evaluate
for seed in (11, 5, 23): print(seed, json.dumps(evaluate(seed)))
