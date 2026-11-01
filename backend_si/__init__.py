"""Legacy imports for the canonical scheduling package."""
from swarmbalance.scheduling.pso import PSOScheduler, PSOOptimizer, Particle
from swarmbalance.scheduling.ga import GAScheduler, GAOptimizer
from swarmbalance.scheduling.fitness import FitnessEvaluator, MultiObjectiveEvaluator
__version__ = "1.0.0"
__all__ = ["PSOScheduler", "PSOOptimizer", "Particle", "GAScheduler", "GAOptimizer", "FitnessEvaluator", "MultiObjectiveEvaluator"]
