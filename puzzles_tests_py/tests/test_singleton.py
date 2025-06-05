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
from chia.wallet.puzzles.singleton_top_layer_v1_1 import (
    launch_conditions_and_coinsol,
    puzzle_for_singleton,
    solution_for_singleton,
    lineage_proof_for_coinsol,
    SINGLETON_LAUNCHER_HASH
) # very important to import the proper version, omitting _v1_1 will import different impl and require different solutions
from chia.types.coin_spend import make_spend


from .utils import load_clvm, dump_list

# Follows example from here: https://chialisp.com/singletons
# To run: pytest puzzles_tests_py/tests/test_singleton.py -k test_singleton_simple -s --disable-warnings
class TestSingleton:

  @pytest_asyncio.fixture(scope='function')
  async def setup(self):
    async with setup_test() as (network, alice, bob):
      await network.farm_block()
      yield network, alice, bob

  @pytest.mark.asyncio
  async def test_singleton_simple(self, setup):
    network: Network
    alice: Wallet
    network, alice, _ = setup
    
    await network.farm_block(farmer=alice)

    PASSWORD_MOD = load_clvm('password')

    password = "hello"
    password_hash = std_hash(password.encode())
    password_puzzle = PASSWORD_MOD.curry(password_hash)
    
    print(f"Password: {password}")
    print(f"Password hash: {password_hash}")
    print(f"Inner puzzle hash: {password_puzzle.get_tree_hash()}")

    # Amount for singleton (must be odd ??? remove odd check and try running the full test to see what happens)
    AMOUNT = uint64(1001)
    print(f"Launch amount: {AMOUNT}")
    
    # Get a coin to launch from
    launch_coin = await alice.choose_coin(AMOUNT)
    assert launch_coin is not None

    alice_balance_start = alice.balance()
    print(f"Alice starting balance: {alice_balance_start}")

    # Get launch conditions and launcher coin spend
    # singleton gets wrapped in launcher here
    conditions, launcher_coinsol = launch_conditions_and_coinsol(
        launch_coin.coin,
        password_puzzle,
        [],  # comment - empty list
        AMOUNT
    )
    
    print(f"Launch conditions: {conditions}")

    # Spend the launch coin to create launcher
    launch_spend = await alice.spend_coin(
        launch_coin,
        pushtx=False,
        custom_conditions=conditions
    )

    # Combine with launcher spend
    combined_spend = SpendBundle.aggregate([launch_spend, SpendBundle([launcher_coinsol], G2Element())])

    # Push the transaction to create the singleton
    result = await network.push_tx(combined_spend)
    print(f"Launch result: {result}")
    
    # block is farmed in push_tx

    # Now we have a singleton! Calculate the launcher coin
    launcher_coin = Coin(launch_coin.coin.name(), SINGLETON_LAUNCHER_HASH, AMOUNT)
    launcher_id = launcher_coin.name()
    
    print()
    print(f"Launcher coin: {launcher_coin}")
    print(f"Launcher ID: {launcher_coin.name()} - parent coin id")
    print(f'Launcher hash: {launch_coin.coin.get_hash()}')

    # The singleton coin
    singleton_puzzle = puzzle_for_singleton(launcher_id, password_puzzle)
    singleton_coin = Coin(launcher_id, singleton_puzzle.get_tree_hash(), AMOUNT)

    print()
    print(f"Singleton puzzle hash: {singleton_puzzle.get_tree_hash()}")
    print(f"Singleton coin: {singleton_coin}")

    # Verify the singleton was created
    singleton_records = await network.sim_client.get_coin_records_by_puzzle_hash(singleton_puzzle.get_tree_hash())
    print(f"Singleton records: {dump_list(singleton_records)}")
    assert len(singleton_records) == 1
    assert singleton_records[0].coin == singleton_coin

    # Test spending the singleton with correct password
    # Create lineage proof for eve spend (first spend of singleton)
    lineage_proof = lineage_proof_for_coinsol(launcher_coinsol)
    
    print()
    print(f"Lineage proof: {lineage_proof}")

    # Inner solution: password + conditions
    # The singleton must recreate itself, so we need to create a new singleton with odd amount
    # We'll also send some coins to alice
    alice_amount = 100  # Send some to alice
    new_singleton_amount = AMOUNT - alice_amount  # Rest continues as singleton
    
    inner_solution = Program.to([
        password,
        [
            [ConditionOpcode.CREATE_COIN, password_puzzle.get_tree_hash(), new_singleton_amount], # Recreate singleton from the inner puzzle hash
            [ConditionOpcode.CREATE_COIN, alice.puzzle_hash, alice_amount],                       # alice sends the amount back to herself
        ]
    ])
    
    print()
    print(f"Inner solution: {inner_solution}")
    print(f"Alice gets: {alice_amount}, New singleton gets: {new_singleton_amount}")
    
    # Solution for singleton
    singleton_solution = solution_for_singleton(
        lineage_proof,
        AMOUNT,
        inner_solution
    )
    
    print()
    print(f"Singleton solution: {singleton_solution}")

    # Spend the singleton
    singleton_spend = make_spend(
        singleton_coin,
        singleton_puzzle,
        singleton_solution
    )
    
    alice_balance_previous = alice.balance() # update the balance

    result = await network.push_tx(SpendBundle([singleton_spend], G2Element()))
    print(f"Singleton spend result: {result}")

    # Check alice got her portion
    assert alice.balance() == alice_balance_previous + alice_amount
    # Verify the new singleton was created
    new_singleton_coin = Coin(singleton_coin.name(), singleton_puzzle.get_tree_hash(), uint64(new_singleton_amount))
    print(f"Expected new singleton coin: {new_singleton_coin}")
    
    singleton_records_after = await network.sim_client.get_coin_records_by_puzzle_hash(singleton_puzzle.get_tree_hash())
    print("")
    print(f"Singleton records after spend: {dump_list(singleton_records_after)}")
    
    # Should have 2 records: the spent original and the new one
    assert len(singleton_records_after) == 2
    spent_singletons = [r for r in singleton_records_after if r.spent_block_index > 0]
    unspent_singletons = [r for r in singleton_records_after if r.spent_block_index == 0]
    assert len(spent_singletons) == 1  # Original spent
    assert len(unspent_singletons) == 1  # New one created
    assert unspent_singletons[0].coin == new_singleton_coin
    
    