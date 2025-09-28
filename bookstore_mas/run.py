import argparse
from .model import LibraryModel

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=5)
    args = parser.parse_args()

    model = LibraryModel(restock_threshold=1)
    model.run(steps=args.steps)
