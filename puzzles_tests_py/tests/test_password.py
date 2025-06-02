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

class TestPasswordPuzzle:

  @pytest_asyncio.fixture(scope="function")
  async def setup(self):
    async with setup_test() as (network, alice, bob):
      await network.farm_block()
      yield network, alice, bob

  
  @pytest.mark.asyncio
  async def test_password_puzzle(self, setup):
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
    old_balance = alice.balance()
    print(f'Alice\'s starting balance {old_balance}')
    print(f'Password puzzle hash: {puzzle_hash}')
    
    print(f'--- Deploying the password puzzle ---')
    password_coin: CoinWrapper | None = await alice.launch_smart_coin(program, amt=LOCK_AMOUNT)
    assert password_coin is not None
    assert alice.balance() == old_balance - LOCK_AMOUNT

    # The password puzzle contains this coin
    print(f'password_coin.puzzle_hash: {password_coin.puzzle_hash}')
    print(f'password_coin.amount: {password_coin.amount}')
    
    # alice provides a solution to the puzzle
    bundle = await alice.spend_coin(
      password_coin, 
      pushtx=False,
      args=Program.to(["hello", []])
    )
    
    # coins are removed from the puzzle program
    result = await network.push_tx(SpendBundle.aggregate([bundle])) 

    print(f"result: {result}")
    assert old_balance == alice.balance() + LOCK_AMOUNT



