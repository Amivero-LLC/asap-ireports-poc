"""Scoring the output of an iReports run.

**Scoring is separate from running, on purpose.** A run costs real money and is nondeterministic;
scoring a saved run file costs nothing and is exact. So everything here reads
`spikes/lambda_demo/out/*.json` — the run's own accounting plus its envelope — rather than
invoking anything. Pay for the analysis once, score it as many times as the harness improves.

That split is the whole design. Without it, every improvement to a check means re-paying for the
runs it checks, and a harness nobody can afford to run is a harness nobody runs.
"""
