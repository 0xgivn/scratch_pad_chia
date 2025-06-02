from __future__ import annotations

import pytest
import pytest_asyncio
from typing import AsyncGenerator, Tuple, Optional

from chia.types.blockchain_format.coin import Coin
from chia.types.spend_bundle import SpendBundle
from chia.types.condition_opcodes import ConditionOpcode

from .piggybank_drivers import (
  create_piggybank_puzzle,
  solution_for_piggybank,
  piggybank_announcement_assertion
)

from cdv.test import setup as setup_test
from cdv.test import Network, Wallet, CoinWrapper

class TestStandardTransaction:

  @pytest_asyncio.fixture(scope="function")
  async def setup(self) -> AsyncGenerator[Tuple[Network, Wallet, Wallet], None]:
    async with setup_test() as (network, alice, bob):
      await network.farm_block()
      yield network, alice, bob

  async def make_and_spend_piggybank(self, network, alice: Wallet, bob: Wallet, CONTRIBUTION_AMOUNT):
    # Get alice wallet some money
    await network.farm_block(farmer=alice)
    
    # Use 1 XCH to create our piggybank on the blockchain; this creates a new coin on the network
    piggybank_coin: CoinWrapper | None = await alice.launch_smart_coin(create_piggybank_puzzle(1_000_000_000_000, bob.puzzle_hash))
    assert piggybank_coin is not None

    # Retrieve a coin that is at least the contribution amount
    contribution_coin: CoinWrapper | None = await alice.choose_coin(CONTRIBUTION_AMOUNT)
    assert contribution_coin is not None

    # Spend of the piggy bank coin.
    piggybank_spend = await alice.spend_coin(
      piggybank_coin,
      pushtx=False, # don't immediately push the tx to the network
      args=solution_for_piggybank(piggybank_coin.coin, CONTRIBUTION_AMOUNT) # pass solution to puzzle
    )

    # Sending change from the contribution to ourself
    contribution_spend = await alice.spend_coin(
      contribution_coin,
      pushtx=False,
      amt=(contribution_coin.amount - CONTRIBUTION_AMOUNT),
      custom_conditions=[
        # conditions emitted when supplying coins, order matters
        # this is like asserting for events
        [ConditionOpcode.CREATE_COIN, contribution_coin.puzzle_hash, (contribution_coin.amount - CONTRIBUTION_AMOUNT)],
        piggybank_announcement_assertion(piggybank_coin.coin, CONTRIBUTION_AMOUNT)
      ]
    )

    # Aggregate spends to execute them together
    combined_spend = SpendBundle.aggregate([contribution_spend, piggybank_spend])

    result = await network.push_tx(combined_spend)
    return result
  
  @pytest.mark.asyncio
  async def test_piggybank_contribution(self, setup):
    network: Network
    alice: Wallet
    bob: Wallet
    network, alice, bob = setup

    try:
      result = await self.make_and_spend_piggybank(network, alice, bob, 500)
      print(f"Transaction result: {result}")  # Add this to see the full error

      assert "error" not in result

      filtered_result = list(filter(
        lambda addition:
          (addition.amount == 501) and # puzzle contains 1 mojo on deploy + 500 contrib amount
          (addition.puzzle_hash == create_piggybank_puzzle(1_000_000_000_000, bob.puzzle_hash).get_tree_hash())
      ,result["additions"]
      ))
      assert len(filtered_result) == 1
    finally:
      # no close method, just pass
      # await network.close()
      pass

  @pytest.mark.asyncio
  async def test_piggybank_completion(self, setup):
    network: Network
    alice: Wallet
    bob: Wallet
    network, alice, bob = setup

    try:
      result = await self.make_and_spend_piggybank(network, alice, bob, 1_000_000_000_000)
      print(f"Transaction result: {result}")  # Add this to see the full error

      assert "error" not in result

      # piggybank puzzle with amount 0
      filtered_result = list(filter(
        lambda addition:
          (addition.amount == 0) and 
          (addition.puzzle_hash == create_piggybank_puzzle(1_000_000_000_000, bob.puzzle_hash).get_tree_hash())
      ,result["additions"]
      ))
      assert len(filtered_result) == 1

      # bob's puzzle hash received the coins upon completion
      filtered_result = list(filter(
        lambda addition:
          (addition.amount == 1_000_000_000_001) and
          (addition.puzzle_hash == bob.puzzle_hash)
      ,result["additions"]
      ))
      assert len(filtered_result) == 1
    finally:
      # no close method, just pass
      # await network.close()
      pass

  @pytest.mark.asyncio
  async def test_piggybank_stealing(self, setup):
    network: Network
    alice: Wallet
    bob: Wallet
    network, alice, bob = setup

    try:
      # negative amount tries to withdraw money
      result = await self.make_and_spend_piggybank(network, alice, bob, -100)
      assert "error" in result
      assert "GENERATOR_RUNTIME_ERROR" in result["error"]
    finally:
      # no close method, just pass
      # await network.close()
      pass