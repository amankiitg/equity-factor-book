# Multiple-Testing Ledger

Append-only. One row per signal run, including every failed variant. Written by the engine in `efb/hygiene.py`, never edited by hand. The row count is a stored number in sprints/E7.

| run_id | signal | variant | horizon | ic_mean | t_stat | deflated_sharpe | hlz_t_hurdle | bonferroni_t | verdict | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | momentum_12_1 | raw_h1 | 1 | 0.015076 | 4.461 | inf | 4.461 | 1.96 | PASS |  |
| 2 | momentum_12_1 | raw_h5 | 5 | 0.01568 | 2.443 | NA | 2.443 | 2.241 | PASS | decay horizon |
| 3 | momentum_12_1 | raw_h21 | 21 | 0.010644 | 1.501 | NA | 1.501 | 2.394 | PASS | decay horizon |
| 4 | momentum_12_1 | raw_h63 | 63 | 0.008241 | 1.214 | NA | 1.214 | 2.498 | PASS | decay horizon |
| 5 | momentum_12_1 | neutralized_h21 | 21 | -0.010684 | -1.549 | NA | 1.549 | 2.576 | PASS | factor-neutral via the exact in-model projection |
| 6 | short_term_reversal | raw_h1 | 1 | 0.012031 | 4.709 | -0.1832 | 4.709 | 2.638 | NULL |  |
| 7 | short_term_reversal | raw_h5 | 5 | 0.016125 | 3.81 | NA | 3.81 | 2.69 | NULL | decay horizon |
| 8 | short_term_reversal | raw_h21 | 21 | 0.01111 | 2.538 | NA | 2.538 | 2.734 | NULL | decay horizon |
| 9 | short_term_reversal | raw_h63 | 63 | 0.009637 | 2.196 | NA | 2.196 | 2.773 | NULL | decay horizon |
| 10 | short_term_reversal | neutralized_h21 | 21 | 0.002796 | 0.609 | NA | 0.609 | 2.807 | NULL | factor-neutral via the exact in-model projection |
| 11 | idio_momentum | raw_h1 | 1 | 0.012102 | 5.044 | 0.0158 | 5.044 | 2.838 | PASS |  |
| 12 | idio_momentum | raw_h5 | 5 | 0.012435 | 2.719 | NA | 2.719 | 2.865 | PASS | decay horizon |
| 13 | idio_momentum | raw_h21 | 21 | 0.008334 | 1.583 | NA | 1.583 | 2.891 | PASS | decay horizon |
| 14 | idio_momentum | raw_h63 | 63 | 0.007081 | 1.433 | NA | 1.433 | 2.914 | PASS | decay horizon |
| 15 | idio_momentum | neutralized_h21 | 21 | -0.003094 | -0.512 | NA | 0.512 | 2.935 | PASS | factor-neutral via the exact in-model projection |
| 16 | low_residual_volatility | raw_h1 | 1 | -0.0014 | -0.464 | -0.9948 | 0.464 | 2.955 | NULL |  |
| 17 | low_residual_volatility | raw_h5 | 5 | -0.012976 | -2.277 | NA | 2.277 | 2.974 | NULL | decay horizon |
| 18 | low_residual_volatility | raw_h21 | 21 | -0.028309 | -4.185 | NA | 4.185 | 2.991 | NULL | decay horizon |
| 19 | low_residual_volatility | raw_h63 | 63 | -0.054505 | -7.658 | NA | 7.658 | 3.008 | NULL | decay horizon |
| 20 | low_residual_volatility | neutralized_h21 | 21 | 0.001865 | 0.327 | NA | 0.327 | 3.023 | NULL | factor-neutral via the exact in-model projection |
| 21 | short_interest | raw_h1 | 1 | 0.002677 | 1.42 | 0.7285 | 1.42 | 3.038 | NULL |  |
| 22 | short_interest | raw_h5 | 5 | 0.005749 | 1.597 | NA | 1.597 | 3.052 | NULL | decay horizon |
| 23 | short_interest | raw_h21 | 21 | 0.010431 | 2.39 | NA | 2.39 | 3.065 | NULL | decay horizon |
| 24 | short_interest | raw_h63 | 63 | 0.013702 | 3.126 | NA | 3.126 | 3.078 | NULL | decay horizon |
| 25 | short_interest | neutralized_h21 | 21 | 0.008518 | 1.176 | NA | 1.176 | 3.09 | NULL | factor-neutral via the exact in-model projection |
| 26 | post_earnings_drift | raw_h1 | 1 | 0.201498 | 21.146 | 1.0033 | 21.146 | 3.102 | PASS |  |
| 27 | post_earnings_drift | raw_h5 | 5 | 0.234347 | 25.492 | NA | 25.492 | 3.113 | PASS | decay horizon |
| 28 | post_earnings_drift | raw_h21 | 21 | 0.19872 | 19.666 | NA | 19.666 | 3.124 | PASS | decay horizon |
| 29 | post_earnings_drift | raw_h63 | 63 | 0.14986 | 13.781 | NA | 13.781 | 3.134 | PASS | decay horizon |
| 30 | post_earnings_drift | neutralized_h21 | 21 | 0.014701 | 1.89 | NA | 1.89 | 3.144 | PASS | factor-neutral via the exact in-model projection |
| 32 | post_earnings_drift | raw_h1 | 1 | 0.201498 | 21.146 | inf | 21.146 | 1.96 | PASS |  |
| 33 | post_earnings_drift | raw_h5 | 5 | 0.234347 | 25.492 | NA | 25.492 | 2.241 | PASS | decay horizon |
| 34 | post_earnings_drift | raw_h21 | 21 | 0.19872 | 19.666 | NA | 19.666 | 2.394 | PASS | decay horizon |
| 35 | post_earnings_drift | raw_h63 | 63 | 0.14986 | 13.781 | NA | 13.781 | 2.498 | PASS | decay horizon |
| 36 | post_earnings_drift | neutralized_h21 | 21 | 0.014701 | 1.89 | NA | 1.89 | 2.576 | PASS | factor-neutral via the exact in-model projection |
| 37 | post_earnings_drift | raw_h1 | 1 | 0.123986 | 14.046 | inf | 14.046 | 1.96 | NULL |  |
| 38 | post_earnings_drift | raw_h5 | 5 | 0.105174 | 11.141 | NA | 11.141 | 2.241 | NULL | decay horizon |
| 39 | post_earnings_drift | raw_h21 | 21 | 0.10295 | 10.304 | NA | 10.304 | 2.394 | NULL | decay horizon |
| 40 | post_earnings_drift | raw_h63 | 63 | 0.071382 | 6.607 | NA | 6.607 | 2.498 | NULL | decay horizon |
| 41 | post_earnings_drift | neutralized_h21 | 21 | 0.009876 | 1.31 | NA | 1.31 | 2.576 | NULL | factor-neutral via the exact in-model projection |
| 1 | momentum_12_1 | raw_h1 | 1 | 0.015076 | 4.461 | inf | 4.461 | 1.96 | PASS |  |
| 2 | momentum_12_1 | raw_h5 | 5 | 0.01568 | 2.443 | NA | 2.443 | 2.241 | PASS | decay horizon |
| 3 | momentum_12_1 | raw_h21 | 21 | 0.010644 | 1.501 | NA | 1.501 | 2.394 | PASS | decay horizon |
| 4 | momentum_12_1 | raw_h63 | 63 | 0.008241 | 1.214 | NA | 1.214 | 2.498 | PASS | decay horizon |
| 5 | momentum_12_1 | neutralized_h21 | 21 | -0.010684 | -1.549 | NA | 1.549 | 2.576 | PASS | factor-neutral via the exact in-model projection |
| 6 | short_term_reversal | raw_h1 | 1 | 0.012031 | 4.709 | -0.1832 | 4.709 | 2.638 | NULL |  |
| 7 | short_term_reversal | raw_h5 | 5 | 0.016125 | 3.81 | NA | 3.81 | 2.69 | NULL | decay horizon |
| 8 | short_term_reversal | raw_h21 | 21 | 0.01111 | 2.538 | NA | 2.538 | 2.734 | NULL | decay horizon |
| 9 | short_term_reversal | raw_h63 | 63 | 0.009637 | 2.196 | NA | 2.196 | 2.773 | NULL | decay horizon |
| 10 | short_term_reversal | neutralized_h21 | 21 | 0.002796 | 0.609 | NA | 0.609 | 2.807 | NULL | factor-neutral via the exact in-model projection |
| 11 | idio_momentum | raw_h1 | 1 | 0.012102 | 5.044 | 0.0158 | 5.044 | 2.838 | PASS |  |
| 12 | idio_momentum | raw_h5 | 5 | 0.012435 | 2.719 | NA | 2.719 | 2.865 | PASS | decay horizon |
| 13 | idio_momentum | raw_h21 | 21 | 0.008334 | 1.583 | NA | 1.583 | 2.891 | PASS | decay horizon |
| 14 | idio_momentum | raw_h63 | 63 | 0.007081 | 1.433 | NA | 1.433 | 2.914 | PASS | decay horizon |
| 15 | idio_momentum | neutralized_h21 | 21 | -0.003094 | -0.512 | NA | 0.512 | 2.935 | PASS | factor-neutral via the exact in-model projection |
| 16 | low_residual_volatility | raw_h1 | 1 | -0.0014 | -0.464 | -0.9948 | 0.464 | 2.955 | NULL |  |
| 17 | low_residual_volatility | raw_h5 | 5 | -0.012976 | -2.277 | NA | 2.277 | 2.974 | NULL | decay horizon |
| 18 | low_residual_volatility | raw_h21 | 21 | -0.028309 | -4.185 | NA | 4.185 | 2.991 | NULL | decay horizon |
| 19 | low_residual_volatility | raw_h63 | 63 | -0.054505 | -7.658 | NA | 7.658 | 3.008 | NULL | decay horizon |
| 20 | low_residual_volatility | neutralized_h21 | 21 | 0.001865 | 0.327 | NA | 0.327 | 3.023 | NULL | factor-neutral via the exact in-model projection |
| 21 | short_interest | raw_h1 | 1 | 0.002677 | 1.42 | 0.7285 | 1.42 | 3.038 | NULL |  |
| 22 | short_interest | raw_h5 | 5 | 0.005749 | 1.597 | NA | 1.597 | 3.052 | NULL | decay horizon |
| 23 | short_interest | raw_h21 | 21 | 0.010431 | 2.39 | NA | 2.39 | 3.065 | NULL | decay horizon |
| 24 | short_interest | raw_h63 | 63 | 0.013702 | 3.126 | NA | 3.126 | 3.078 | NULL | decay horizon |
| 25 | short_interest | neutralized_h21 | 21 | 0.008518 | 1.176 | NA | 1.176 | 3.09 | NULL | factor-neutral via the exact in-model projection |
| 26 | post_earnings_drift | raw_h1 | 1 | 0.123986 | 14.046 | 0.4285 | 14.046 | 3.102 | NULL |  |
| 27 | post_earnings_drift | raw_h5 | 5 | 0.105174 | 11.141 | NA | 11.141 | 3.113 | NULL | decay horizon |
| 28 | post_earnings_drift | raw_h21 | 21 | 0.10295 | 10.304 | NA | 10.304 | 3.124 | NULL | decay horizon |
| 29 | post_earnings_drift | raw_h63 | 63 | 0.071382 | 6.607 | NA | 6.607 | 3.134 | NULL | decay horizon |
| 30 | post_earnings_drift | neutralized_h21 | 21 | 0.009876 | 1.31 | NA | 1.31 | 3.144 | NULL | factor-neutral via the exact in-model projection |
| 1 | momentum_12_1 | raw_h1 | 1 | 0.015076 | 4.461 | inf | 4.461 | 1.96 | PASS |  |
| 2 | momentum_12_1 | raw_h5 | 5 | 0.01568 | 2.443 | NA | 2.443 | 2.241 | PASS | decay horizon |
| 3 | momentum_12_1 | raw_h21 | 21 | 0.010644 | 1.501 | NA | 1.501 | 2.394 | PASS | decay horizon |
| 4 | momentum_12_1 | raw_h63 | 63 | 0.008241 | 1.214 | NA | 1.214 | 2.498 | PASS | decay horizon |
| 5 | momentum_12_1 | neutralized_h21 | 21 | -0.010684 | -1.549 | NA | 1.549 | 2.576 | PASS | factor-neutral via the exact in-model projection |
| 6 | short_term_reversal | raw_h1 | 1 | 0.012031 | 4.709 | -0.1832 | 4.709 | 2.638 | NULL |  |
| 7 | short_term_reversal | raw_h5 | 5 | 0.016125 | 3.81 | NA | 3.81 | 2.69 | NULL | decay horizon |
| 8 | short_term_reversal | raw_h21 | 21 | 0.01111 | 2.538 | NA | 2.538 | 2.734 | NULL | decay horizon |
| 9 | short_term_reversal | raw_h63 | 63 | 0.009637 | 2.196 | NA | 2.196 | 2.773 | NULL | decay horizon |
| 10 | short_term_reversal | neutralized_h21 | 21 | 0.002796 | 0.609 | NA | 0.609 | 2.807 | NULL | factor-neutral via the exact in-model projection |
| 11 | idio_momentum | raw_h1 | 1 | 0.012102 | 5.044 | 0.0158 | 5.044 | 2.838 | PASS |  |
| 12 | idio_momentum | raw_h5 | 5 | 0.012435 | 2.719 | NA | 2.719 | 2.865 | PASS | decay horizon |
| 13 | idio_momentum | raw_h21 | 21 | 0.008334 | 1.583 | NA | 1.583 | 2.891 | PASS | decay horizon |
| 14 | idio_momentum | raw_h63 | 63 | 0.007081 | 1.433 | NA | 1.433 | 2.914 | PASS | decay horizon |
| 15 | idio_momentum | neutralized_h21 | 21 | -0.003094 | -0.512 | NA | 0.512 | 2.935 | PASS | factor-neutral via the exact in-model projection |
| 16 | low_residual_volatility | raw_h1 | 1 | -0.0014 | -0.464 | -0.9948 | 0.464 | 2.955 | NULL |  |
| 17 | low_residual_volatility | raw_h5 | 5 | -0.012976 | -2.277 | NA | 2.277 | 2.974 | NULL | decay horizon |
| 18 | low_residual_volatility | raw_h21 | 21 | -0.028309 | -4.185 | NA | 4.185 | 2.991 | NULL | decay horizon |
| 19 | low_residual_volatility | raw_h63 | 63 | -0.054505 | -7.658 | NA | 7.658 | 3.008 | NULL | decay horizon |
| 20 | low_residual_volatility | neutralized_h21 | 21 | 0.001865 | 0.327 | NA | 0.327 | 3.023 | NULL | factor-neutral via the exact in-model projection |
| 21 | short_interest | raw_h1 | 1 | 0.002677 | 1.42 | 0.7285 | 1.42 | 3.038 | NULL |  |
| 22 | short_interest | raw_h5 | 5 | 0.005749 | 1.597 | NA | 1.597 | 3.052 | NULL | decay horizon |
| 23 | short_interest | raw_h21 | 21 | 0.010431 | 2.39 | NA | 2.39 | 3.065 | NULL | decay horizon |
| 24 | short_interest | raw_h63 | 63 | 0.013702 | 3.126 | NA | 3.126 | 3.078 | NULL | decay horizon |
| 25 | short_interest | neutralized_h21 | 21 | 0.008518 | 1.176 | NA | 1.176 | 3.09 | NULL | factor-neutral via the exact in-model projection |
| 26 | post_earnings_drift | raw_h1 | 1 | 0.123986 | 14.046 | 0.4285 | 14.046 | 3.102 | NULL |  |
| 27 | post_earnings_drift | raw_h5 | 5 | 0.105174 | 11.141 | NA | 11.141 | 3.113 | NULL | decay horizon |
| 28 | post_earnings_drift | raw_h21 | 21 | 0.10295 | 10.304 | NA | 10.304 | 3.124 | NULL | decay horizon |
| 29 | post_earnings_drift | raw_h63 | 63 | 0.071382 | 6.607 | NA | 6.607 | 3.134 | NULL | decay horizon |
| 30 | post_earnings_drift | neutralized_h21 | 21 | 0.009876 | 1.31 | NA | 1.31 | 3.144 | NULL | factor-neutral via the exact in-model projection |
| 102 | short_interest | raw_h1 | 1 | 0.002677 | 1.42 | inf | 1.42 | 1.96 | NULL |  |
| 103 | short_interest | raw_h5 | 5 | 0.005749 | 1.597 | NA | 1.597 | 2.241 | NULL | decay horizon |
| 104 | short_interest | raw_h21 | 21 | 0.010431 | 2.39 | NA | 2.39 | 2.394 | NULL | decay horizon |
| 105 | short_interest | raw_h63 | 63 | 0.013702 | 3.126 | NA | 3.126 | 2.498 | NULL | decay horizon |
| 106 | short_interest | neutralized_h21 | 21 | 0.008518 | 1.176 | NA | 1.176 | 2.576 | NULL | factor-neutral via the exact in-model projection |
| 107 | post_earnings_drift | raw_h1 | 1 | 0.123986 | 14.046 | 0.4603 | 14.046 | 2.638 | NULL |  |
| 108 | post_earnings_drift | raw_h5 | 5 | 0.105174 | 11.141 | NA | 11.141 | 2.69 | NULL | decay horizon |
| 109 | post_earnings_drift | raw_h21 | 21 | 0.10295 | 10.304 | NA | 10.304 | 2.734 | NULL | decay horizon |
| 110 | post_earnings_drift | raw_h63 | 63 | 0.071382 | 6.607 | NA | 6.607 | 2.773 | NULL | decay horizon |
| 111 | post_earnings_drift | neutralized_h21 | 21 | 0.009876 | 1.31 | NA | 1.31 | 2.807 | NULL | factor-neutral via the exact in-model projection |
