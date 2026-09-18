Your sole task is to evaluate the OUTCOME of the current step and decide what happens next.
Base your decision on what was actually accomplished, not on how the reasoning is phrased.

Select NEXT_STEP if:
    - The step produced partial progress but the user's original goal is not yet fully satisfied.
    - The step revealed a new sub-task, error, or dependency that must be resolved before proceeding.
    - A tool/action was executed and its result now needs to be processed, validated, or acted upon.

Select END if:
    - The outcome fully and correctly satisfies the user's original request (final answer delivered).
    - Proceeding further requires user confirmation, a decision, or missing input that only the user can provide.
    - The step failed or reached a dead end that cannot be resolved without user input.

Constraint: Output only the selection (NEXT_STEP or END). No explanation, no punctuation, no additional text.