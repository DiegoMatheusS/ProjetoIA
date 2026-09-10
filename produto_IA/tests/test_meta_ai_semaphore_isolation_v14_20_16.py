import asyncio

from src import api


def test_meta_ai_endpoint_does_not_wait_for_analyze_queue(monkeypatch):
    async def scenario():
        analyze_queue = asyncio.Semaphore(1)
        await analyze_queue.acquire()  # simula /analisar ou navegador ocupado

        monkeypatch.setattr(api, "_analyze_semaphore", analyze_queue)
        monkeypatch.setattr(api, "_meta_ai_semaphore", asyncio.Semaphore(1))
        monkeypatch.setattr(
            api,
            "_meta_ai_whatsapp_enrich_sync",
            lambda payload: {"utilizado": True, "fonte": "META_AI_WHATSAPP"},
        )

        request = api.MetaAiWhatsappEnrichmentRequest(
            categoria="PROCESSADOR",
            nome="AMD Ryzen teste",
            payload={},
            resposta="Socket: AM5",
            forcar=True,
        )

        try:
            result = await asyncio.wait_for(
                api.enriquecer_com_meta_ai_whatsapp(request, x_api_key=None),
                timeout=0.5,
            )
        finally:
            analyze_queue.release()

        assert result["utilizado"] is True
        assert result["fonte"] == "META_AI_WHATSAPP"

    asyncio.run(scenario())


def test_technical_ai_endpoint_has_own_queue(monkeypatch):
    async def scenario():
        analyze_queue = asyncio.Semaphore(1)
        await analyze_queue.acquire()

        monkeypatch.setattr(api, "_analyze_semaphore", analyze_queue)
        monkeypatch.setattr(api, "_technical_ai_semaphore", asyncio.Semaphore(1))
        monkeypatch.setattr(
            api,
            "_technical_ai_enrich_sync",
            lambda payload: {"utilizado": True, "provedor": "GEMINI"},
        )

        request = api.TechnicalAiEnrichmentRequest(
            provedor="GEMINI",
            categoria="PROCESSADOR",
            nome="AMD Ryzen teste",
            payload={},
            somentePreencheLacunas=True,
        )

        try:
            result = await asyncio.wait_for(
                api.enriquecer_com_ia_tecnica(request, x_api_key=None),
                timeout=0.5,
            )
        finally:
            analyze_queue.release()

        assert result["utilizado"] is True
        assert result["provedor"] == "GEMINI"

    asyncio.run(scenario())


def test_semaphore_defaults_are_separate():
    assert api._meta_ai_semaphore is not api._analyze_semaphore
    assert api._technical_ai_semaphore is not api._analyze_semaphore
    assert api._meta_ai_semaphore is not api._technical_ai_semaphore
