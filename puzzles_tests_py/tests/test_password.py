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
    bob: Wallet
    network, alice, bob = setup
    
    await network.farm_block(farmer=alice)

    password_hash = std_hash(b"hello")
    
    PASSWORD_MOD = load_clvm("password")
    program = PASSWORD_MOD.curry(password_hash)
    puzzle_hash = program.get_tree_hash()

    # now alice will spend some coins to turn it to password locked coin

    # first fetch our unspent coin from blockchain
    LOCK_AMOUNT = 1_000
    password_spend = await alice.choose_coin(LOCK_AMOUNT)
    assert password_spend is not None

    # build solution for puzzle
    solution = Program.to([
      # Lock amount in puzzle
      [ConditionOpcode.CREATE_COIN, puzzle_hash, LOCK_AMOUNT],
      # the amount thats left, returned to alice
      [ConditionOpcode.CREATE_COIN, alice.puzzle_hash, password_spend.amount - LOCK_AMOUNT]
    ])

    old_balance = alice.balance()

    # await alice.spend_coin(
    #   spend_coin, 
    #   pushtx=True,
    #   args=solution
    # )

    # network.farm_block()
    # assert old_balance == alice.balance() + LOCK_AMOUNT

    password_coin: CoinWrapper | None = await alice.launch_smart_coin(program)
    assert password_coin is not None

    bundle = await alice.spend_coin(
      password_coin, 
      pushtx=False,
      args=solution
    )
    
    result = await network.push_tx(SpendBundle.aggregate([bundle])) 
    await network.farm_block()
    print(f"result: {result}")




