from chia.types.blockchain_format.coin import Coin
from chia_rs.sized_bytes import bytes32
from chia.types.blockchain_format.program import Program
from chia.types.condition_opcodes import ConditionOpcode
from chia_rs.sized_ints import uint64
from chia.util.hash import std_hash

from clvm.casts import int_to_bytes

from .utils import load_clvm

PIGGYBANK_MOD = load_clvm("piggybank")

def create_piggybank_puzzle(amount, cash_out_puzzlehash):
    return PIGGYBANK_MOD.curry(amount, cash_out_puzzlehash)

# build call arguments
def solution_for_piggybank(pb_coin: Coin, contribution_amount):
    # chialisp pseudo code
    return Program.to([pb_coin.amount, (pb_coin.amount + contribution_amount), pb_coin.puzzle_hash])

# make condition to assert announcement
def piggybank_announcement_assertion(pb_coin: Coin, contribution_amount):
    # ASSERT_COIN_ANNOUNCEMENT deprecated for SEND_MESSAGE / RECEIVE_MESSAGE - https://chialisp.com/conditions/#66-send_message https://chialisp.com/conditions/#about-message-conditions-mode-parameter
    # this condition means: if you don't see this announcement, don't spend
    return [ConditionOpcode.ASSERT_COIN_ANNOUNCEMENT, std_hash(pb_coin.name() + int_to_bytes(pb_coin.amount + contribution_amount))]

