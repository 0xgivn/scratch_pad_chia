import time

from chia._tests.util.spend_sim import SimClient, SpendSim
from chia.types.blockchain_format.program import Program
from chia.types.coin_spend import make_spend
from chia.types.condition_opcodes import ConditionOpcode
from chia.types.mempool_inclusion_status import MempoolInclusionStatus
from chia.util.hash import std_hash
from chia_rs.sized_ints import uint64
from chia_rs import CoinSpend, G2Element, SpendBundle
from clvm_tools import clvmc

# to run: python puzzles_tests_py/src/smart_coin.py
# example from: https://gist.github.com/trepca/d6a0d7f761de7459643422eb73c435e6
async def main():
    sim: SpendSim
    async with SpendSim.managed() as sim:
        # set simulators time to current time
        sim.pass_time(uint64(time.time()))
        # rpc client to simulator "node"
        client: SimClient = SimClient(sim)
        # this puzzle passes any conditions it receives without any validation
        anyone_can_spend_puzzle = Program.to(1)
        # get a puzzle hash for it
        acs_ph = anyone_can_spend_puzzle.get_tree_hash()
        # farm some coins to acs_ph
        await sim.farm_block(acs_ph)

        # compile password clsp from https://chialisp.com/chialisp-first-smart-coin/
        password_clsp = '''
;;; This puzzle locks coins with a password.
;;; It should not be used for production purposes.
;;; Use a password that has no meaning to you, preferably random.
(mod (
        PASSWORD_HASH ; This is the sha256 hash of the password.
        password ; This is the original password used in the password hash.
        conditions ; An arbitrary list of conditions to output.
    )
    ; If the hash of the password matches,
    (if (= (sha256 password) PASSWORD_HASH)
        ; Output the conditions list.
        conditions
        ; Otherwise, throw an error.
        (x)
    )
)
        '''
        password_puzzle = Program.to(clvmc.compile_clvm_text(password_clsp, []))
        secret_password_puzzle = password_puzzle.curry(std_hash(b"SUPER SECRET PASSWORD"))
        # get a puzzle hash for it
        secret_password_ph = secret_password_puzzle.get_tree_hash()
        # now we'll spend our coin to turn it to password locked coin
        # first fetch our unspent coin from blockchain
        our_coin_records = await client.get_coin_records_by_puzzle_hash(acs_ph, include_spent_coins=False)
        our_coin = our_coin_records[0].coin
        original_amount = sum([coin.coin.amount for coin in our_coin_records])

        solution = Program.to([
            # we're going to lock 10_000_000 mojos with our password - solution for puzzle
            [ConditionOpcode.CREATE_COIN, secret_password_ph, 10_000_000],
            # whatever is left will be returned to us
            [ConditionOpcode.CREATE_COIN, acs_ph, our_coin.amount - 10_000_000]
        ])
        coin_spend = make_spend(our_coin, anyone_can_spend_puzzle, solution)
        # now we can spend our coin by pushing it to the simulator
        # first need to create a spend bundle or more traditionally called a transaction
        bundle = SpendBundle([coin_spend],
                             # G2Element() means empty signature, we don't need signatures since our coin doesn't
                             # require them
                             G2Element())
        # push the bundle to the simulator
        await client.push_tx(bundle)

        # now we farm another block to save our spends to blockchain
        await sim.farm_block()

        # let check that we spent 10_000_000 mojos to our password locked coin
        our_coin_records = await client.get_coin_records_by_puzzle_hash(acs_ph, include_spent_coins=False)
        assert sum([cr.coin.amount for cr in our_coin_records]) == original_amount - 10_000_000

        # let's now try to spend our password locked coin
        # first fetch our unspent coin from blockchain
        password_protected_coins = await client.get_coin_records_by_puzzle_hash(secret_password_ph,
                                                                                include_spent_coins=False)
        # we should have only one coin
        password_protected_coin = password_protected_coins[0].coin
        # we'll try to spend it with wrong password
        wrong_solution = Program.to(["WRONG PASSWORD", [ConditionOpcode.CREATE_COIN, acs_ph, 10_000_000]])
        wrong_coin_spend: CoinSpend = make_spend(password_protected_coin, secret_password_puzzle, wrong_solution)
        # we can run this spend locally to see if it's valid
        puzzle = wrong_coin_spend.puzzle_reveal.to_program()
        # run the puzzle with the solution
        try:
            puzzle.run(wrong_coin_spend.solution)
            assert False, "This should not happen"
        except ValueError:
            pass

        # now we'll try to spend it with the correct password
        correct_solution = Program.to(
            [b"SUPER SECRET PASSWORD",
             # we're creating a new coin back to us (our puzzle hash)
             [[ConditionOpcode.CREATE_COIN, acs_ph, 10_000_000]]
            ])
        correct_coin_spend: CoinSpend = make_spend(password_protected_coin, secret_password_puzzle, correct_solution)
        bundle = SpendBundle([correct_coin_spend], G2Element())
        status, err = await client.push_tx(bundle)
        # this should go through
        assert status == MempoolInclusionStatus.SUCCESS
        await sim.farm_block()

        # check if there are any password locked coins left
        password_protected_coins = await client.get_coin_records_by_puzzle_hash(secret_password_ph,
                                                                                include_spent_coins=False)
        assert len(password_protected_coins) == 0
        # let's check that we spent our password locked coin and that we got 10_000_000 mojos back
        our_coin_records = await client.get_coin_records_by_puzzle_hash(acs_ph, include_spent_coins=False)
        our_balance = sum([coin.coin.amount for coin in our_coin_records])
        assert our_balance == original_amount, f"Expected {original_amount}, got {our_balance}"
        print("All good.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())