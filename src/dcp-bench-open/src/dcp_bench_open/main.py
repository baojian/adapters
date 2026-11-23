"""Local pilot generator; the full/parity datasets are not implemented yet."""
import argparse
from pathlib import Path
from .adapter import DCPBenchOpenAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True, help="Expanded pinned v0.3.0 source")
    parser.add_argument("--solver-image-archive", type=Path, required=True, help="docker save of dcp-eval/cpmpy_python:v1")
    parser.add_argument("--solver-image-id", required=True, help="docker image inspect --format '{{.Id}}' identity")
    parser.add_argument("--docker-binary-image", default="docker:28.2.2-dind")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--task-ids", nargs="+")
    parser.add_argument("--control", choices=("correct", "incorrect", "unsat", "suboptimal"), default="correct")
    parser.add_argument("--controls-dir", type=Path)
    DCPBenchOpenAdapter(**vars(parser.parse_args())).run()


if __name__ == "__main__":
    main()
