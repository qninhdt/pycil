"""FSRS-4.5 default weights (w0..w16), hardcoded — never per-user fit.

Source: open-spaced-repetition/fsrs4anki v4.5 default parameters. These 17
weights are the published defaults used for every user (the product deliberately
skips per-user optimization; see docs/designs/fsrs-learning-engine.md §8).
"""

W: tuple[float, ...] = (
    0.4,   # w0  init stability (Again)
    0.6,   # w1  init stability (Hard, unused)
    2.4,   # w2  init stability (Good)
    5.8,   # w3  init stability (Easy, unused)
    4.93,  # w4  init difficulty base
    0.94,  # w5  init difficulty grade factor
    0.86,  # w6  difficulty linear damping
    0.01,  # w7  difficulty mean-reversion weight
    1.49,  # w8  stability success base
    0.14,  # w9  stability success exponent
    0.94,  # w10 stability success retrievability factor
    2.18,  # w11 stability failure base
    0.05,  # w12 stability failure difficulty exponent
    0.34,  # w13 stability failure stability exponent
    1.26,  # w14 stability failure retrievability factor
    0.29,  # w15 (Hard penalty, unused)
    2.61,  # w16 (Easy bonus, unused)
)

assert len(W) == 17, "FSRS-4.5 uses exactly 17 weights"
