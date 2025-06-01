from chia.types.blockchain_format.coin import Coin
# from chia.types.blockchain_format.sized_bytes import bytes32
from chia_rs.sized_bytes import bytes32
from chia.types.blockchain_format.program import Program
from chia.types.condition_opcodes import ConditionOpcode
# from chia.util.ints import uint64
from chia_rs.sized_ints import uint64
from chia.util.hash import std_hash

from clvm.casts import int_to_bytes

# from cdv.util.load_clvm import load_clvm
# from clvm_tools_rs import compile_clvm, start_clvm_program
# Program.from_bytes should replace load_clvm

# from chia_puzzles_py.programs import (

# )

from clvm_tools.clvmc import compile_clvm

path = compile_clvm(
  "puzzles/piggybank.clsp", "puzzles/piggybank.clsp.hex", ["puzzles/include"])

with open(path, 'r') as f:
    hex_content = f.read().strip()
program_bytes = bytes.fromhex(hex_content)

PIGGYBANK_MOD = Program.from_bytes(program_bytes)

def create_piggybank_puzzle(amount, cash_out_puzzlehash):
    return PIGGYBANK_MOD.curry(amount, cash_out_puzzlehash)

# build call arguments
def solution_for_piggybank(pb_coin: Coin, contribution_amount):
    # chialisp pseudo code
    return Program.to([pb_coin.amount, (pb_coin.amount + contribution_amount), pb_coin.puzzle_hash])

# make condition to assert announcement
def piggybank_announcement_assertion(pb_coin: Coin, contribution_amount):
    return [ConditionOpcode.ASSERT_COIN_ANNOUNCEMENT, std_hash(pb_coin.name() + int_to_bytes(pb_coin.amount + contribution_amount))]

