from __future__ import annotations

import pytest
import pytest_asyncio
from typing import AsyncGenerator, Tuple

from chia.types.blockchain_format.coin import Coin
from chia.types.spend_bundle import SpendBundle
from chia.types.condition_opcodes import ConditionOpcode

from .piggybank_drivers import (
  create_piggybank_puzzle,
  solution_for_piggybank,
  piggybank_announcement_assertion
)

from cdv.test import setup as setup_test
from cdv.test import Network, Wallet

class TestStandardTransaction:

  @pytest_asyncio.fixture(scope="function")
  async def setup(self) -> AsyncGenerator[Tuple[Network, Wallet, Wallet], None]:
    async with setup_test() as (network, alice, bob):
      await network.farm_block()
      yield network, alice, bob

  async def make_and_spend_piggybank(self, network, alice, bob, CONTRIBUTION_AMOUNT):
    # Get alice wallet some money
    await network.farm_block(farmer=alice)

    # Use 1 XCH to create our piggybank on the blockchain
    piggybank_coin: Coin = await alice.launch_smart_coin(create_piggybank_puzzle(1_000_000_000_000, bob.puzzle_hash))

    # Retrieve a coin that is at least the contribution amount
    contribution_coin: Coin = await alice.choose_coin(CONTRIBUTION_AMOUNT)

    # Spend of the piggy bank coin.
    piggybank_spend = await alice.spend_coin(
      piggybank_coin,
      pushtx=False, # don't immediately push the tx to the network
      args=solution_for_piggybank(piggybank_coin, CONTRIBUTION_AMOUNT) # pass solution to puzzle
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
        piggybank_announcement_assertion(piggybank_coin, CONTRIBUTION_AMOUNT)
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
          (addition.amount == 501) and
          (addition.puzzle_hash == create_piggybank_puzzle(1_000_000_000_000, bob.puzzle_hash).get_tree_hash())
      ,result["additions"]
      ))
      assert len(filtered_result) == 1
    finally:
      # no close method, just pass
      # await network.close()
      pass
