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
# To run: pytest puzzles_tests_py/tests/test_singleton.py -k test_singleton_state_update -s --disable-warnings
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
    print()
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

  # e2e example showing how singleton state updates while maintaining identity
  @pytest.mark.asyncio
  async def test_singleton_state_update(self, setup):
    network: Network
    alice: Wallet
    bob: Wallet # we use bob's balance as a tracker that we successfully unlocked password puzzle
    network, alice, bob = setup
    
    await network.farm_block(farmer=alice)

    PASSWORD_MOD = load_clvm('password')
    AMOUNT = uint64(1001)
    
    print("\n\n**************** REAL-WORLD PASSWORD PUZZLE EXAMPLE ****************")
    
    # ==============================================
    # STEP 1: Create singleton with password "hello"
    # ==============================================
    print("\n=== STEP 1: Creating singleton with password 'hello' ===")
    
    password1 = "hello"
    password1_hash = std_hash(password1.encode())
    inner_puzzle1 = PASSWORD_MOD.curry(password1_hash)
    
    launch_coin = await alice.choose_coin(AMOUNT)
    assert launch_coin is not None
    
    conditions, launcher_coinsol = launch_conditions_and_coinsol(
        launch_coin.coin, inner_puzzle1, [], AMOUNT
    )
    
    launch_spend = await alice.spend_coin(launch_coin, pushtx=False, custom_conditions=conditions)
    combined_spend = SpendBundle.aggregate([launch_spend, SpendBundle([launcher_coinsol], G2Element())])
    await network.push_tx(combined_spend)
    
    # Calculate singleton identity (THIS NEVER CHANGES)
    launcher_coin = Coin(launch_coin.coin.name(), SINGLETON_LAUNCHER_HASH, AMOUNT)
    LAUNCHER_ID = launcher_coin.name()  # ← This is the persistent identity!
    
    print(f'🔑 Singleton Identity LAUNCHER_ID: {LAUNCHER_ID} \n\t   ---> this never changes, it is a parent coin id')
    print(f"📝 Current password: '{password1}'")
    
    # Current singleton coin with password1
    singleton_puzzle1 = puzzle_for_singleton(LAUNCHER_ID, inner_puzzle1)
    singleton_coin1 = Coin(LAUNCHER_ID, singleton_puzzle1.get_tree_hash(), AMOUNT)
    print(f"📍 Singleton ph 1: {singleton_puzzle1.get_tree_hash()}")
    
    # ==============================================
    # STEP 2: Use singleton with password "hello" (normal usage)
    # ==============================================
    print("\n=== STEP 2: Using singleton with password 'hello' ===")
    
    send_amount1 = 100
    continue_amount1 = AMOUNT - send_amount1
    
    lineage_proof1 = lineage_proof_for_coinsol(launcher_coinsol)
    inner_solution1 = Program.to([
      password1,  # Use current password to unlock
      [
        [ConditionOpcode.CREATE_COIN, bob.puzzle_hash, send_amount1],
        [ConditionOpcode.CREATE_COIN, inner_puzzle1.get_tree_hash(), continue_amount1]  # Continue with SAME password
      ]
    ])
    
    singleton_solution1 = solution_for_singleton(lineage_proof1, AMOUNT, inner_solution1)
    singleton_spend1 = make_spend(singleton_coin1, singleton_puzzle1, singleton_solution1)
    
    await network.push_tx(SpendBundle([singleton_spend1], G2Element()))
    
    # New singleton coin with same password (SAME LaunchID, SAME inner puzzle)
    singleton_coin1b = Coin(singleton_coin1.name(), singleton_puzzle1.get_tree_hash(), uint64(continue_amount1))
    
    print(f"✅ Spent singleton using password '{password1}'")
    print(f"💰 Alice received: {send_amount1} mojos")
    print(f"🔄 Singleton continues with same password, amount: {continue_amount1}")
    print(f"🔄 singleton_coin1b: {singleton_coin1b.to_json_dict()}")
    assert bob.balance() == send_amount1
    
    
    # ==============================================
    # STEP 3: Use singleton again BUT change password to "world"
    # ==============================================
    print("\n=== STEP 3: Using singleton again, but changing password to 'world' ===")
    
    password2 = "world"
    password2_hash = std_hash(password2.encode())
    inner_puzzle2 = PASSWORD_MOD.curry(password2_hash)  # ← NEW inner puzzle!
    
    print(f"📝 Changing password from '{password1}' to '{password2}'")
    
    send_amount2 = 50
    new_amount = continue_amount1 - send_amount2
    
    lineage_proof2 = lineage_proof_for_coinsol(singleton_spend1)
    inner_solution2 = Program.to([
        password1,  # Use OLD password to unlock
        [
            [ConditionOpcode.CREATE_COIN, bob.puzzle_hash, send_amount2],
            [ConditionOpcode.CREATE_COIN, inner_puzzle2.get_tree_hash(), new_amount]  # ← NEW inner puzzle!
        ]
    ])
    
    singleton_solution2 = solution_for_singleton(lineage_proof2, uint64(continue_amount1), inner_solution2)
    singleton_spend2 = make_spend(singleton_coin1b, singleton_puzzle1, singleton_solution2)
    
    await network.push_tx(SpendBundle([singleton_spend2], G2Element()))
    
    # New singleton coin with password2 (SAME LaunchID, DIFFERENT inner puzzle)
    singleton_puzzle2 = puzzle_for_singleton(LAUNCHER_ID, inner_puzzle2)  # ← SAME LaunchID!
    singleton_coin2 = Coin(singleton_coin1b.name(), singleton_puzzle2.get_tree_hash(), uint64(new_amount))
    
    print(f"✅ Password updated successfully")
    print(f"🔑 Singleton Id (LaunchID): {LAUNCHER_ID} \n\t ^^^^^ all descend from here")  # ← UNCHANGED!
    print(f"📍 New singleton address: {singleton_puzzle2.get_tree_hash()}")  # ← CHANGED!
    assert bob.balance() == send_amount1 + send_amount2
    
    # ==============================================
    # STEP 4: Use singleton with NEW password "world" (same usage pattern)
    # ==============================================
    print("\n=== STEP 4: Using singleton with NEW password 'world' ===")
    
    send_amount3 = 50
    final_amount = new_amount - send_amount3
    
    lineage_proof3 = lineage_proof_for_coinsol(singleton_spend2)
    inner_solution3 = Program.to([
        password2,  # Use NEW password to unlock, old won't work
        [
            [ConditionOpcode.CREATE_COIN, bob.puzzle_hash, send_amount3],
            [ConditionOpcode.CREATE_COIN, inner_puzzle2.get_tree_hash(), final_amount]  # Continue with NEW password
        ]
    ])
    
    singleton_solution3 = solution_for_singleton(lineage_proof3, uint64(new_amount), inner_solution3)
    singleton_spend3 = make_spend(singleton_coin2, singleton_puzzle2, singleton_solution3)
    
    result = await network.push_tx(SpendBundle([singleton_spend3], G2Element()))
    print(f"✅ Spent singleton using NEW password '{password2}'")
    print(f"💰 Bob received: {send_amount3} mojos")
    print(f"🔄 Singleton continues with new password, amount: {final_amount}")
    
    final_singleton_coin = Coin(singleton_coin2.name(), singleton_puzzle2.get_tree_hash(), uint64(final_amount))
    print(f"📍 Final singleton address: {singleton_puzzle2.get_tree_hash()}")
    assert bob.balance() == send_amount1 + send_amount2 + send_amount3
    
    print("\n🎯 RECAP:")
    print(f"   • Singleton Identity NEVER changes: {LAUNCHER_ID}")
    print(f"   • When state changes the singleton ph also changes, but through the lineage we prove its the same singleton")
    print(f"   • State evolution happens through CREATE_COIN conditions")
    print(f"   • State change frontrun is impossible because spend bundle will revert")
    print(f"   • Usage pattern stays the same: know current password + use same API")
    print(f"   • External parties need to track current state to interact")
    print(f"   • Each spend creates lineage for the next spend")
    