"""The generic federal layer — what any US expatriate faces, wherever they live.

Split from `tax/us/residence/`, which answers only what a particular treaty governs, the
way PolicyEngine splits `gov/irs` from `gov/states/xx`. Nothing here may read a treaty
rule, and nothing here may read a residence-country tax treatment (invariant #2).
"""
