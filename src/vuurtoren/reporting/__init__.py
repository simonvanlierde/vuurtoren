"""Read-only reporting helpers. Nothing here can move a projection — it reads one.

Kept out of `tax/` deliberately: a filing threshold is not a tax rule, and the two answer
different questions about the same account. `fbar.py` says so where the rules diverge.
"""
