"""KrishiMini-20M Foundation Model Factory.

Owns: architecture → tokenizer contract → scratch pretraining → eval gates.
Does not replace packages/models (LoRA/registry); this is the scratch path.
"""

from foundation_model.architecture.config import KrishiMiniConfig, load_config
from foundation_model.architecture.param_count import ParamBreakdown, count_parameters
from foundation_model.architecture.validation import validate_architecture

__all__ = [
    "KrishiMiniConfig",
    "ParamBreakdown",
    "count_parameters",
    "load_config",
    "validate_architecture",
]
