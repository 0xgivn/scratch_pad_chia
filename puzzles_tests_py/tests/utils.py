from chia.types.blockchain_format.program import Program

from puzzles import load_puzzle

def load_clvm(puzzle_name: str) -> Program:
    return Program.from_bytes(bytes(load_puzzle(puzzle_name)))

def dump_list(lst: list) -> str:
    output = ""
    for e in lst:
        output = f"{output} {e}" if output else f"({e}"
    return output + ")"