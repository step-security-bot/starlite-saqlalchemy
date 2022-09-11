import asyncio

import pydantic.fields
import starlite
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from starlite_lib import sentry
from starlite_lib.client import HttpClient
from starlite_lib.db import engine
from starlite_lib.redis import redis
from starlite_lib.starlite.middleware import DBSessionMiddleware
from starlite_lib.worker import Worker, WorkerFunction, queue

from . import compression, health, logging, openapi
from .dependencies import filters, session
from .exceptions import logging_exception_handler
from .response import Response


class Starlite(starlite.Starlite):
    """
    Wrapper around [`starlite.Starlite`][starlite.app.Starlite] that abstracts boilerplate, with
    the following differences:

    - `compression_config` and `openapi_config` are omitted as parameters and set internally
    - Adds an after-request handler that commits or rolls back the db session based on HTTP status
    code of response.
    - Provides the standard collection route filter dependencies.
    - Adds `handler_functions` param and registers them on an SAQ `Worker` instance.
    - Registers shutdown handlers for the worker, http client, database and redis.
    - Registers startup handlers for logging, sentry and the worker.
    - Adds a health check route handler that serves on `/health` by default and returns json
    representation of app settings.
    """

    def __init__(
        self,
        *,
        after_request: starlite.types.AfterRequestHookHandler | None = None,
        after_response: starlite.types.AfterResponseHookHandler | None = None,
        allowed_hosts: list[str] | None = None,
        before_request: starlite.types.BeforeRequestHookHandler | None = None,
        cors_config: starlite.config.CORSConfig | None = None,
        csrf_config: starlite.config.CSRFConfig | None = None,
        dependencies: dict[str, starlite.Provide] | None = None,
        exception_handlers: dict[int | type[Exception], starlite.types.ExceptionHandler]
        | None = None,
        guards: list[starlite.types.Guard] | None = None,
        middleware: list[starlite.types.Middleware] | None = None,
        on_shutdown: list[starlite.types.LifeSpanHandler] | None = None,
        on_startup: list[starlite.types.LifeSpanHandler] | None = None,
        parameters: dict[str, pydantic.fields.FieldInfo] | None = None,
        plugins: list[starlite.plugins.PluginProtocol] | None = None,
        response_cookies: list[starlite.datastructures.Cookie] | None = None,
        response_headers: dict[str, starlite.datastructures.ResponseHeader] | None = None,
        route_handlers: list[starlite.types.ControllerRouterHandler],
        static_files_config: starlite.config.StaticFilesConfig
        | list[starlite.config.StaticFilesConfig]
        | None = None,
        template_config: starlite.config.TemplateConfig | None = None,
        tags: list[str] | None = None,
        worker_functions: list[WorkerFunction | tuple[str, WorkerFunction]] | None = None,
    ):

        dependencies = dependencies or {}
        dependencies.setdefault("filters", starlite.Provide(filters))
        dependencies.setdefault("session", starlite.Provide(session))

        exception_handlers = exception_handlers or {}
        exception_handlers.setdefault(HTTP_500_INTERNAL_SERVER_ERROR, logging_exception_handler)

        middleware = [DBSessionMiddleware] + (middleware or [])  # type:ignore

        on_shutdown = on_shutdown or []
        on_shutdown.extend([HttpClient.close, engine.dispose, redis.close])

        on_startup = on_startup or []
        on_startup.extend([logging.log_config.configure, sentry.configure])

        worker_functions = worker_functions or []
        # only instantiate the worker if necessary
        if worker_functions:
            worker = Worker(queue, worker_functions or [])

            async def worker_on_app_startup() -> None:
                loop = asyncio.get_running_loop()
                loop.create_task(worker.start())

            on_shutdown.append(worker.stop)
            on_startup.append(worker_on_app_startup)

        route_handlers.append(health.health_check)

        super().__init__(
            after_request=after_request,
            after_response=after_response,
            allowed_hosts=allowed_hosts,
            before_request=before_request,
            compression_config=compression.config,
            cors_config=cors_config,
            csrf_config=csrf_config,
            dependencies=dependencies,
            exception_handlers=exception_handlers,
            guards=guards,
            middleware=middleware,
            on_shutdown=on_shutdown,
            on_startup=on_startup,
            openapi_config=openapi.config,
            parameters=parameters,
            plugins=plugins,
            response_class=Response,
            response_cookies=response_cookies,
            response_headers=response_headers,
            route_handlers=route_handlers,
            static_files_config=static_files_config,
            template_config=template_config,
            tags=tags,
        )
