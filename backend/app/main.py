import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, caja, comercial, finanzas, inventario, produccion, usuarios
from app.core.config import get_settings
from app.core.errors import register_exception_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    es_prod = settings.env == "production"

    app = FastAPI(
        title="Panadería · ERP/POS",
        version="2.0.0",
        # En producción no publicamos la documentación interactiva
        docs_url=None if es_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if es_prod else "/api/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", settings.csrf_header_name, "Authorization"],
        )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/v1"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    register_exception_handlers(app)

    v1 = APIRouter(prefix="/api/v1")
    for modulo in (auth, usuarios, caja, inventario, produccion, comercial, finanzas):
        v1.include_router(modulo.router)
    app.include_router(v1)

    @app.get("/api/health", tags=["Sistema"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
