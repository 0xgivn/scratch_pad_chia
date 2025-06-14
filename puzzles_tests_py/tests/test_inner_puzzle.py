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
from chia_rs.sized_ints import uint64
from chia_rs.sized_bytes import bytes32
from chia_rs import G2Element
from chia_rs import AugSchemeMPL, G1Element, G2Element, PrivateKey


from .utils import load_clvm, dump_list

# Follows example from here: https://docs.chia.net/guides/crash-course/inner-puzzles/
# To run: pytest puzzles_tests_py/tests/test_inner_puzzle.py -k test_simple_inner_puzzle -s --disable-warnings
# To run: pytest puzzles_tests_py/tests/test_inner_puzzle.py -k test_inner_puzzle -s --disable-warnings
# To run: pytest puzzles_tests_py/tests/test_inner_puzzle.py -k test_alice_gets_bobs_funds -s --disable-warnings
class TestInnerPuzzle:

  @pytest_asyncio.fixture(scope='function')
  async def setup(self):
    async with setup_test() as (network, alice, bob):
      await network.farm_block()
      yield network, alice, bob

  @pytest.mark.asyncio
  async def test_simple_inner_puzzle(self, setup):
    network: Network
    alice: Wallet
    network, alice, bob = setup
    
    await network.farm_block(farmer=alice)

    INNER_PUZZLE_MOD = load_clvm('inner_puzzle')
    REQUIRED_BLOCKS = 20
    inner_puzzle_program = INNER_PUZZLE_MOD.curry(REQUIRED_BLOCKS)
    pk = alice.pk()
    print(f'alice\'s pk: {pk}')

    OUTER_PUZZLE_MOD = load_clvm('outer_puzzle')
    outer_puzzle_program = OUTER_PUZZLE_MOD.curry(pk, inner_puzzle_program)

    FUND_AMOUNT = 1000
    send_coin = await alice.choose_coin(FUND_AMOUNT)
    assert send_coin is not None

    alice_balance_start = alice.balance()
    outer_puzzle_coin: CoinWrapper | None = await alice.launch_smart_coin(outer_puzzle_program, amt=FUND_AMOUNT)
    assert outer_puzzle_coin is not None
    assert alice_balance_start == alice.balance() + FUND_AMOUNT # alice sent coins to outer_puzzle

    solution = Program.to([[[[ConditionOpcode.CREATE_COIN, alice.puzzle_hash, FUND_AMOUNT]]]])

    # pass the time
    for _ in range(REQUIRED_BLOCKS):
      await network.farm_block(farmer=bob)

    spend_result = await alice.spend_coin(outer_puzzle_coin, pushtx=True, args=solution)
    assert spend_result.__dict__['error'] is None

    await network.farm_block()

    # fetch coins for outer_puzzle
    records = await network.sim_client.get_coin_records_by_puzzle_hash(outer_puzzle_program.get_tree_hash())
    print(f'\ncoin records of outer_puzzle_program hash')
    print(f'{dump_list(records)}')

    # alice was able to retrieve her coins after the REQUIRED_BLOCKS passed
    assert alice.balance() == alice_balance_start
  
  @pytest.mark.asyncio
  async def test_inner_puzzle(self, setup):
    network: Network
    alice: Wallet
    network, alice, bob = setup
    
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

    # pass the time
    for _ in range(REQUIRED_BLOCKS):
      await network.farm_block(farmer=bob) 

    # its not possible for bob to provide the solution with puzzle's coin
    # spend_result = await bob.spend_coin(outer_puzzle_coin, pushtx=True, args=solution)
    # print(f'spend_result: {spend_result.__dict__}')

    # bob donates to outer_puzzle
    BOBS_FUNDING: uint64 = uint64(100)
    bobs_coin: CoinWrapper | None = await bob.choose_coin(BOBS_FUNDING)
    assert bobs_coin is not None

    bobs_spend = await bob.spend_coin(
        bobs_coin,
        pushtx=True,
        amt=BOBS_FUNDING, 
        custom_conditions=[
          [ConditionOpcode.CREATE_COIN, outer_puzzle_program.get_tree_hash(), BOBS_FUNDING]
        ]
      )
    print(f'\nbobs_spend to outer_puzzle: {bobs_spend.__dict__}')
    await network.farm_block()

    # fetch coins for outer_puzzle
    records = await network.sim_client.get_coin_records_by_puzzle_hash(outer_puzzle_program.get_tree_hash())
    print(f'\ncoin records of outer_puzzle_program hash')
    print(f'{dump_list(records)}')

    # Bob spending the coins he just sent to the outer_puzzle - not possible
    # puzzle_bob_coin = CoinWrapper(bob.puzzle_hash, BOBS_FUNDING, outer_puzzle_program)
    # spend_result = await bob.spend_coin(puzzle_bob_coin, pushtx=True, args=Program.to([[[[ConditionOpcode.CREATE_COIN, bob.puzzle_hash, BOBS_FUNDING]]]]))
    # print(f'spend_result: {spend_result.__dict__}')

    # Bob tries to provide a signed solution to the puzzle and send himself back the donated amount
    # outer_puzzle pub key assertion fails
    
    # ASSERTION FAILS
    # spend_result = await bob.spend_coin(
    #   CoinWrapper(records[1].coin.parent_coin_info, BOBS_FUNDING, outer_puzzle_program),
    #   pushtx=True, 
    #   args=Program.to([[[[ConditionOpcode.CREATE_COIN, bob.puzzle_hash, BOBS_FUNDING]]]])
    # )
    # print(f'\nbob tries to supply solution: {spend_result.__dict__}')
    # assert "error" in spend_result.__dict__
    # assert "GENERATOR_RUNTIME_ERROR" in spend_result.__dict__['error']


    # alice was able to retrieve her coins after the REQUIRED_BLOCKS passed
    assert alice.balance() == alice_balance_start
    
  @pytest.mark.asyncio
  async def test_alice_gets_bobs_funds(self, setup):
    network: Network
    alice: Wallet
    network, alice, bob = setup
    
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

    # pass the time
    for _ in range(REQUIRED_BLOCKS):
      await network.farm_block(farmer=bob) 

    # bob donates to outer_puzzle
    BOBS_FUNDING: uint64 = uint64(100)
    bobs_coin: CoinWrapper | None = await bob.choose_coin(BOBS_FUNDING)
    assert bobs_coin is not None

    bobs_spend = await bob.spend_coin(
        bobs_coin,
        pushtx=True,
        amt=BOBS_FUNDING, 
        custom_conditions=[
          [ConditionOpcode.CREATE_COIN, outer_puzzle_program.get_tree_hash(), BOBS_FUNDING]
        ]
      )
    print(f'\nbobs_spend to outer_puzzle: {bobs_spend.__dict__}')
    await network.farm_block()

    # fetch coins for outer_puzzle
    records = await network.sim_client.get_coin_records_by_puzzle_hash(outer_puzzle_program.get_tree_hash())
    print(f'\ncoin records of outer_puzzle_program hash')
    print(f'{dump_list(records)}')

    # Alice spends both puzzle coins (see the records above)
    spend_alice_1 = await alice.spend_coin(
      CoinWrapper(records[0].coin.parent_coin_info, FUND_AMOUNT, outer_puzzle_program), 
      pushtx=False,
      args=Program.to([[[[ConditionOpcode.CREATE_COIN, alice.puzzle_hash, FUND_AMOUNT]]]])
    )

    spend_alice_2 = await alice.spend_coin(
      CoinWrapper(records[1].coin.parent_coin_info, BOBS_FUNDING, outer_puzzle_program), 
      pushtx=False,
      args=Program.to([[[[ConditionOpcode.CREATE_COIN, alice.puzzle_hash, BOBS_FUNDING]]]])
    )

    combined_spend = SpendBundle.aggregate([spend_alice_1, spend_alice_2])

    # We have to move REQUIRED_BLOCKS further, so we can get bobs donation coins
    for _ in range(REQUIRED_BLOCKS):
      await network.farm_block(farmer=bob) 

    result = await network.push_tx(combined_spend)

    print(f'alice gets outer_puzzles coins: {result}')

    # Alice owns all couns from outer_puzzle (including bob's donation)
    assert alice.balance() == alice_balance_start + BOBS_FUNDING
    