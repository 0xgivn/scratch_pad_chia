from __future__ import annotations

import pytest
import pytest_asyncio

from chia.types.blockchain_format.coin import Coin
from chia.types.spend_bundle import SpendBundle
from chia.types.condition_opcodes import ConditionOpcode
from chia.util.hash import std_hash
from cdv.test import setup as setup_test
from cdv.test import Network, Wallet, CoinWrapper
from chia_rs.sized_bytes import bytes32
from chia_rs import G2Element
from chia.types.blockchain_format.program import Program

from .utils import load_clvm

# To run: pytest puzzles_tests_py/tests/test_password.py -k test_password_puzzle_no_condition -s --disable-warnings
# To run: pytest puzzles_tests_py/tests/test_password.py -k test_password_send_to_bob -s --disable-warnings
class TestPasswordPuzzle:

  @pytest_asyncio.fixture(scope="function")
  async def setup(self):
    async with setup_test() as (network, alice, bob):
      await network.farm_block()
      yield network, alice, bob

  
  @pytest.mark.asyncio
  async def test_password_puzzle_no_condition(self, setup):
    network: Network
    alice: Wallet
    network, alice, _ = setup
    
    await network.farm_block(farmer=alice)

    password_hash = std_hash(b"hello")
    
    PASSWORD_MOD = load_clvm("password")
    program = PASSWORD_MOD.curry(password_hash)
    puzzle_hash = program.get_tree_hash()
    LOCK_AMOUNT = 1_000

    # now alice will spend some coins to turn it to password locked coin
    alice_start_balance = alice.balance()
    print(f'Alice\'s starting balance {alice_start_balance}')
    print(f'Password puzzle hash: {puzzle_hash}')
    
    print(f'--- Deploying the password puzzle ---')
    password_coin: CoinWrapper | None = await alice.launch_smart_coin(program, amt=LOCK_AMOUNT)
    assert password_coin is not None
    assert alice.balance() == alice_start_balance - LOCK_AMOUNT

    # The password coin contains the password puzzle
    print(f'password_coin.puzzle_hash: {password_coin.puzzle_hash}')
    print(f'password_coin.amount: {password_coin.amount}')
    
    # alice provides correct solution to the puzzle
    bundle = await alice.spend_coin(
      password_coin, 
      pushtx=False,
      args=Program.to(["hello", []]) # coins are sent to ph, no conditions so coins are burned
    )
    
    result = await network.push_tx(SpendBundle.aggregate([bundle])) 

    print(f"result: {result}")
    # the coins are no longer in alice's balance
    assert alice_start_balance - LOCK_AMOUNT == alice.balance()

    # the coins aren't in the password ph as well (they are spent)
    password_puzzle_coins = await network.sim_client.get_coin_records_by_puzzle_hash(puzzle_hash, include_spent_coins=False)
    print(f"password puzzle coins: {password_puzzle_coins}")
    assert len(password_puzzle_coins) == 0

  # Alice answers correct password and adds a condition which sends the coin to Bob
  @pytest.mark.asyncio
  async def test_password_send_to_bob(self, setup):
    network: Network
    alice: Wallet
    bob: Wallet
    network, alice, bob = setup
    print(f"\nalice's ph: {alice.puzzle_hash}")
    print(f"bob's ph: {bob.puzzle_hash}")
    
    await network.farm_block(farmer=alice)

    password_hash = std_hash(b"hello")
    
    PASSWORD_MOD = load_clvm("password")
    program = PASSWORD_MOD.curry(password_hash)
    puzzle_hash = program.get_tree_hash()
    print(f"password ph: {puzzle_hash}")
    LOCK_AMOUNT = 1_000

    # now alice will spend some coins to turn it to password locked coin
    alice_start_balance = alice.balance()
    bob_start_balance = bob.balance()
    print("")
    print(f"alice_start_balance: {alice_start_balance}")
    print(f"bob_start_balance: {bob_start_balance}")
    
    password_coin: CoinWrapper | None = await alice.launch_smart_coin(program, amt=LOCK_AMOUNT)
    assert password_coin is not None
    assert alice.balance() == alice_start_balance - LOCK_AMOUNT

    # alice provides a solution to the puzzle
    bundle = await alice.spend_coin(
      password_coin, 
      pushtx=False,
      args=Program.to([
        "hello",
        [
          [ConditionOpcode.CREATE_COIN, bob.puzzle_hash, LOCK_AMOUNT],
        ]
      ])
    )
    
    # coins are removed from the puzzle program
    result = await network.push_tx(SpendBundle.aggregate([bundle])) 

    print(f"result: {result}")
    assert alice_start_balance - LOCK_AMOUNT == alice.balance() # alice's balance stays the same
    assert bob_start_balance + LOCK_AMOUNT == bob.balance() # bob received the coin after password unlock

    # some more queries
    password_puzzle_coins = await network.sim_client.get_coin_records_by_puzzle_hash(puzzle_hash, include_spent_coins=False)
    print("")
    print(f"password puzzle coins: {password_puzzle_coins}")
    assert len(password_puzzle_coins) == 0

    bobs_puzzle_coins = await network.sim_client.get_coin_records_by_puzzle_hash(bob.puzzle_hash, include_spent_coins=False)
    print("")
    print(f"bobs_puzzle_coins: {bobs_puzzle_coins}")
    assert len(bobs_puzzle_coins) == 1
    assert bobs_puzzle_coins[0].coin.amount == LOCK_AMOUNT



