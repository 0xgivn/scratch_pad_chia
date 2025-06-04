This repo is used to research and test chialisp code. [Overview](https://www.youtube.com/watch?v=lh9spX6Qv8I) of the coin system, statefulness, puzzles. Developer [summary](https://youtu.be/dEFLJSU87K8?t=1878) of Chia.

Examples are from:
- [Chia Network playlist](https://www.youtube.com/playlist?list=PLmnzWPUjpmaGzFNq2PeMljHNrXGwj2TDY)
- [chia_puzzles](https://github.com/Chia-Network/chia_puzzles)
- [Password Puzzle](https://chialisp.com/chialisp-first-smart-coin/) - first smart coin
- [Inner Puzzles](https://docs.chia.net/guides/crash-course/inner-puzzles/)
- [Minimal smart coin example on Chia blockchain](https://gist.github.com/trepca/d6a0d7f761de7459643422eb73c435e6)
- [Usage of primitives](https://github.com/Chia-Network/chia-blockchain/tree/main/chia/wallet/puzzles) in python - [singleton](https://github.com/Chia-Network/chia-blockchain/blob/main/chia/wallet/puzzles/singleton_top_layer_v1_1.py), etc

More info:
- [Chia Coloured Coins: Technical Guide](https://www.youtube.com/watch?v=17pa2t_FQQM&ab_channel=MattHoward), [part 2](https://www.youtube.com/watch?v=L1umdr-PjJE&ab_channel=MattHoward)
- [Singletons](https://chialisp.com/singletons/)
- [High Level Tips 1 - Managing State, Coin Creation, Announcements](https://www.youtube.com/watch?v=lDXB4NlbQ-E), [part 2](https://www.youtube.com/watch?v=T4noZyNJkFA), [part 3](https://www.youtube.com/watch?v=54heTeWq9xQ)

# Setup

Prerequisites:
- poetry for dependency management
- pyenv to use the correct python version

1. `poetry install`
2. `eval $(poetry env activate)`

# Testing

To run all tests:
`pytest puzzles_tests_py`

To run a test file:
`pytest puzzles_tests_py/tests/test_piggybank.py`

To run a specific test from a file:
`pytest puzzles_tests_py/tests/test_piggybank.py -k test_piggybank_contribution`

To output stdout logs add the `-s` flag.
To omit warnings add `--disable-warnings`.

> `cdv tests` is not available unless you have installed `chia-dev-tools`

You can access alternative blockchain querying API from `network.sim_client`.

# Issues

In the official [docs](https://chialisp.com/chialisp-primer/intro/#installation) (or [these](https://docs.chia.net/guides/crash-course/smart-coins/)) you will be prompted to first install the [chia-dev-tools](https://github.com/Chia-Network/chia-dev-tools/?tab=readme-ov-file#install). This is just a collection of libraries wrapped in a convenient CLI. As of writing this, some of the dependencies don't build for arm64 architecture, which means you might not be able to follow the examples outlined in the official docs. You will still be able to install the dependencies in this project (or any other), build puzzles and run the tests.
