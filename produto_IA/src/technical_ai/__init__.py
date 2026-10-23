from .providers import (
    OpenAIProvider,
    TechnicalAIProvider,
    TechnicalAIProviderError,
    TechnicalAIResponse,
    get_technical_ai_provider,
)
from .service import build_technical_ai_prompt, enrich_hardware_with_external_ai
from .retry_research import run_iterative_external_research_with_retry
from . import service as _service

# Mantém o serviço público inalterado, mas permite uma única recuperação curta
# quando a OpenAI falhar por timeout/rede antes de preencher qualquer campo.
_service.run_iterative_external_research = run_iterative_external_research_with_retry

__all__ = [
    "OpenAIProvider",
    "TechnicalAIProvider",
    "TechnicalAIProviderError",
    "TechnicalAIResponse",
    "get_technical_ai_provider",
    "build_technical_ai_prompt",
    "enrich_hardware_with_external_ai",
]
