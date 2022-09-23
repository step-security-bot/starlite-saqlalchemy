import asyncio
from collections import abc

import starlite
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from starlite.config.app import AppConfig

from starlite_saqpg import sentry
from starlite_saqpg.client import HttpClient
from starlite_saqpg.db import engine
from starlite_saqpg.redis import redis
from starlite_saqpg.worker import Worker, WorkerFunction, queue

from . import db, health, logging, openapi, response
from .dependencies import filters, session
from .exceptions import logging_exception_handler


class ConfigureApp:
    def __init__(self, worker_functions: abc.Collection[WorkerFunction] | None = None) -> None:
        # would rather `worker_functions or []` but this seems to narrow type better
        self.worker_functions = [] if worker_functions is None else worker_functions

    def __call__(self, app_config: AppConfig) -> AppConfig:
        app_config.dependencies.setdefault("filters", starlite.Provide(filters))
        app_config.dependencies.setdefault("session", starlite.Provide(session))
        app_config.exception_handlers.setdefault(
            HTTP_500_INTERNAL_SERVER_ERROR, logging_exception_handler
        )

        if not isinstance(app_config.before_send, list):
            app_config.before_send = [app_config.before_send]
        app_config.before_send.append(db.transaction_manager)

        app_config.on_shutdown.extend([HttpClient.close, engine.dispose, redis.close])
        app_config.on_startup.extend([logging.log_config.configure, sentry.configure])

        if self.worker_functions:
            worker = Worker(queue, self.worker_functions)

            async def worker_on_app_startup() -> None:
                loop = asyncio.get_running_loop()
                loop.create_task(worker.start())

            app_config.on_shutdown.append(worker.stop)
            app_config.on_startup.append(worker_on_app_startup)

        app_config.route_handlers.append(health.health_check)

        if app_config.response_class is None:
            app_config.response_class = response.Response

        if app_config.openapi_config is None:
            app_config.openapi_config = openapi.config

        return app_config