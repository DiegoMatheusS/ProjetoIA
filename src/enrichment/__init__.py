from . import core as _core
from .core import TechnicalEnricher, apply_enrichment
from .identity import build_identity, identity_is_strong
from ..extractors.research_specs import extract_research_specs

# O agente técnico usa um extrator complementar para fontes estruturadas.
# Mantemos ml_specs como base e trocamos apenas a referência usada pelo core
# de enriquecimento, sem afetar os outros fluxos do ProjetoIA.
_core.extract_specs = extract_research_specs

__all__ = ["TechnicalEnricher", "apply_enrichment", "build_identity", "identity_is_strong"]
