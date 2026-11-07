# bench/heldout/run_b.py — `python -m bench.heldout.run_b`: same runner as run.py over the fresh blind set B.
from bench.heldout.run import HERE, main

SET_B = HERE / "set_b"

if __name__ == "__main__":
    main(SET_B)
