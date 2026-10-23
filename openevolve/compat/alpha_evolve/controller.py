"""Async-shaped completion check for synchronous local experiments."""

from .experiment import AlphaEvolveExperiment


async def run_controller_loop(experiment: AlphaEvolveExperiment) -> None:
    """Check completion without running again, polling queues or creating workers.

    The local ``start_experiment`` already ran OpenEvolve to completion. Cloud
    sampler/evaluator/idle-timeout arguments are deliberately unsupported.
    """
    if not isinstance(experiment, AlphaEvolveExperiment):
        raise TypeError("experiment must be the local AlphaEvolveExperiment")
    experiment._require_state("COMPLETED")
