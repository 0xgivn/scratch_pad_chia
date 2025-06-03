from __future__ import annotations

import pytest
import pytest_asyncio

from chia.types.blockchain_format.coin import Coin
from chia.types.spend_bundle import SpendBundle
from chia.types.condition_opcodes import ConditionOpcode
from chia.types.blockchain_format.program import Program
from chia.util.hash import std_hash
from chia.consensus.default_constants import DEFAULT_CONSTANTS
from cdv.test import setup as setup_test
from cdv.test import Network, Wallet, CoinWrapper
from chia_rs.sized_bytes import bytes32
from chia_rs import G2Element
from chia_rs import AugSchemeMPL, G1Element, G2Element, PrivateKey


from .utils import load_clvm

# Follows example from here: https://docs.chia.net/guides/crash-course/inner-puzzles/
# To run: pytest puzzles_tests_py/tests/test_inner_puzzle.py -k test_inner_puzzle -s
class TestInnerPuzzle:

  @pytest_asyncio.fixture(scope='function')
  async def setup(self):
    async with setup_test() as (network, alice, bob):
      await network.farm_block()
      yield network, alice, bob

  
  @pytest.mark.asyncio
  async def test_inner_puzzle(self, setup):
    network: Network
    alice: Wallet
    network, alice, _ = setup
    
    await network.farm_block(farmer=alice)

    INNER_PUZZLE_MOD = load_clvm('inner_puzzle')
    REQUIRED_BLOCKS = 20
    inner_puzzle_program = INNER_PUZZLE_MOD.curry(REQUIRED_BLOCKS)
    pk = alice.pk()
    print(f'alice\'s pk: {pk}')

    OUTER_PUZZLE_MOD = load_clvm('outer_puzzle')
    outer_puzzle_program = OUTER_PUZZLE_MOD.curry(pk, inner_puzzle_program)
    print(f'outer_puzzle_program hash: {outer_puzzle_program.get_tree_hash()}')
    print()


    FUND_AMOUNT = 1000
    send_coin = await alice.choose_coin(FUND_AMOUNT)
    assert send_coin is not None
    print(f'send_coin.parent_coin_info: {send_coin.parent_coin_info}')
    print(f'send_coin.coin.get_hash(): {send_coin.coin.get_hash()}')
    print()

    # this doesn't work - why???
    # -> to create a coin we must provide the puzzle reveal (hex)
    # -> the send_coin contains a puzzle, but its not `outer_puzzle_program`, thus spend below doesn't make sense
    # spend_result = await alice.spend_coin(
    #   send_coin, 
    #   pushtx=True, 
    #   args=Program.to([ConditionOpcode.CREATE_COIN, outer_puzzle_program.get_tree_hash(), FUND_AMOUNT])
    # )
    
    # print(f'alice sends coins to outer puzzle hash: {spend_result.__dict__}')

    alice_balance_start = alice.balance()
    outer_puzzle_coin: CoinWrapper | None = await alice.launch_smart_coin(outer_puzzle_program, amt=FUND_AMOUNT)
    assert outer_puzzle_coin is not None
    assert alice_balance_start == alice.balance() + FUND_AMOUNT

    print(f'outer_puzzle_coin.parent_coin_info: {outer_puzzle_coin.parent_coin_info}')
    print(f'outer_puzzle_coin.puzzle_hash: {outer_puzzle_coin.puzzle_hash}')
    print(f'outer_puzzle_coin.amount: {outer_puzzle_coin.amount}')
    print(f'outer_puzzle_coin.coin.get_hash(): {outer_puzzle_coin.coin.get_hash()}')
    coin_id = std_hash(outer_puzzle_coin.parent_coin_info + outer_puzzle_coin.puzzle_hash + outer_puzzle_coin.amount.to_bytes(8, "big"))
    print(f'outer_puzzle_coin manual hash: {coin_id}')

    # proof that coin id is properly derived
    assert coin_id == outer_puzzle_coin.coin.get_hash()

    solution = Program.to([[[[ConditionOpcode.CREATE_COIN, alice.puzzle_hash, FUND_AMOUNT]]]])
    print(f'solution: {solution}')

    # there's no need to manually sign and create the spend bundle, the spend_coin API does this for us
    # inner_solution_hash = Program.to([[[ConditionOpcode.CREATE_COIN, alice.puzzle_hash, FUND_AMOUNT]]]).get_tree_hash()
    # print(f'inner_solution_hash: {inner_solution_hash}')

    # signature: G2Element = AugSchemeMPL.sign(
    #   alice.sk_,
    #   (inner_solution_hash + coin_id + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA), # or GENESIS_CHALLENGE
    # )

    # print(f'signature.to_json_dict(): {signature.to_json_dict()}')

    spend_result = await alice.spend_coin(outer_puzzle_coin, pushtx=True, args=solution)

    print(f'spend_result: {spend_result.__dict__}')

    # Expected failure because REQUIRED_BLOCKS have not passed
    assert "error" in spend_result.__dict__
    assert "ASSERT_HEIGHT_RELATIVE_FAILED" in spend_result.__dict__['error']

    
    for _ in range(REQUIRED_BLOCKS):
      await network.farm_block()
      

    spend_result = await alice.spend_coin(outer_puzzle_coin, pushtx=True, args=solution)
    assert spend_result.__dict__['error'] == None
    print(f'spend_result: {spend_result.__dict__}')
    