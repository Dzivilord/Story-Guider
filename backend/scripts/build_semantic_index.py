import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.search.semantic import DEFAULT_ARTIFACT_DIR, DEFAULT_DATASET, build_index

parser = argparse.ArgumentParser(description="Build the Goodreads semantic FAISS index")
parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
args = parser.parse_args()
print(build_index(args.dataset, args.artifact_dir))
