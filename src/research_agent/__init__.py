"""Agente de pesquisa técnica do CriaByte.

Esta camada orquestra as fontes técnicas existentes sem alterar o contrato HTTP
usado pelo frontend/backend. O fluxo externo continua usando /ia-tecnica/enriquecer.
"""

from .agent import TechnicalResearchAgent, research_hardware_locally
from .planner import ResearchPlan, build_research_plan

__all__ = [
    "TechnicalResearchAgent",
    "research_hardware_locally",
    "ResearchPlan",
    "build_research_plan",
]
