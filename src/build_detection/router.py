"""API de prévia de PC montado/kit; nunca publica sem confirmação do Admin."""
import os
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from .analyzer import analyze_listing

router = APIRouter(prefix="/anuncios", tags=["PCs e kits de upgrade"])

class CatalogHardware(BaseModel):
    id: int = Field(gt=0)
    categoria: str = Field(min_length=2, max_length=60)
    nome: str = Field(default="", max_length=250)
    marca: str = Field(default="", max_length=120)
    modelo: str = Field(default="", max_length=200)

class AnalyzeListingRequest(BaseModel):
    titulo: str = Field(default="", max_length=500)
    descricao: str = Field(default="", max_length=30000)
    catalogo: list[CatalogHardware] = Field(default_factory=list, max_length=500)

@router.post("/classificar-pc-kit")
def classify_build_listing(payload: AnalyzeListingRequest, x_api_key: str | None = Header(default=None)):
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida ou não configurada")
    try:
        return analyze_listing(payload.titulo, payload.descricao, [c.model_dump() for c in payload.catalogo])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
