"""应用入口：装配中间件、路由与生命周期。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from . import __version__
from .api import admin, app_api, maa, pages
from .config import settings
from .db import init_db
from .web import STATIC_DIR, templates

logger = logging.getLogger("maa_remote")


class PayloadLimitMiddleware(BaseHTTPMiddleware):
    """挡住超大的请求体，避免截图任务把内存打爆。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > settings.max_payload_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": f"请求体超过 {settings.max_payload_bytes // 1024 // 1024} MiB 上限"},
                )
        return await call_next(request)


def create_app() -> FastAPI:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        if settings.using_default_secret:
            logger.warning(
                "正在使用默认 SECRET_KEY，任何人都能伪造登录态。请设置环境变量 MAA_REMOTE_SECRET_KEY！"
            )
        logger.info("MAA 远程控制 v%s 已启动，公开地址：%s", __version__, settings.public_base_url)
        yield

    app = FastAPI(
        title="MAA 远程控制",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(PayloadLimitMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="maa_remote_session",
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(maa.router)
    app.include_router(pages.router)
    app.include_router(admin.router)
    app.include_router(app_api.router)

    @app.exception_handler(pages.LoginRequired)
    async def _handle_login_required(_request: Request, exc: pages.LoginRequired) -> RedirectResponse:
        return RedirectResponse(f"/login?next={quote(exc.next_url)}", status_code=status.HTTP_303_SEE_OTHER)

    @app.exception_handler(admin.AdminRequired)
    async def _handle_admin_required(request: Request, _exc: admin.AdminRequired) -> Response:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"request": request, "user": None, "csrf_token": "", "message": "这个页面只有管理员能访问"},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app()
