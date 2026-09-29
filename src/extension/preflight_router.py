from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from ..criabyte.client import CriaByteApiError
from .preflight import (
    ConfirmAffiliateOfferRequest,
    PrepareAffiliateOfferRequest,
    confirm_offer_sync,
    prepare_offer_sync,
)


router = APIRouter(prefix="/extensao", tags=["Extensão administrativa"])


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


@router.post("/preparar-oferta")
async def prepare_affiliate_offer(
    payload: PrepareAffiliateOfferRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    try:
        return await asyncio.to_thread(prepare_offer_sync, payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CriaByteApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao preparar oferta pela extensão: {exc}",
        ) from exc


@router.post("/confirmar-oferta")
async def confirm_affiliate_offer(
    payload: ConfirmAffiliateOfferRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    try:
        return await asyncio.to_thread(confirm_offer_sync, payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CriaByteApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao confirmar oferta pela extensão: {exc}",
        ) from exc
