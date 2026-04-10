import argparse
import asyncio
import logging
from app.agents.bus.queues import MESSAGE_BUS
from app.agents.tools.mcp.manager import MCP_POOL
from app.channel.cli.entry import CliRuntime,build_parser
from app.config.settings import APP_NAME, APP_VERSION, settings
from app.domains.code_analysis.services.file_analysis_service import FileAnalysisService
from app.domains.code_analysis.services.lsp.lsp_service import CodeLSPService
from app.domains.cron import CRON_MANAGER
from app.infrastructure.database import close_db
from app.infrastructure.redis import REDIS_CONN
from app.infrastructure.storage import STORAGE_CONN
from app.infrastructure.vector_store import VECTOR_STORE_CONN
from app.logger import setup_logging


async def startup_event()->None:
    """Application startup for CLI mode."""
    try:
        logging.info("Starting application...")
        task=asyncio.create_task(MESSAGE_BUS.run())
        setattr(startup_event,"message_bus_task",task)
        logging.info("MessageBus started")

        MCP_POOL.start_idle_cleanup()

        if settings.run_cron:
            CRON_MANAGER.start()
            logging.info("Cron started")
        else:
            logging.info("Cron disabled (RUN_CRON=false)")

        started=FileAnalysisService.start_global_scheduler()
        if started:
            logging.info("Code analysis scheduler started")
        else:
            logging.info("Code analysis scheduler already running")

        logging.info("%s v%s started",APP_NAME,APP_VERSION)
    except Exception as e:
        logging.error("Startup failed: %s",e)
        raise


async def shutdown_event()->None:
    """Application shutdown for CLI mode."""
    task=getattr(startup_event,"message_bus_task",None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logging.info("MessageBus stopped")

    MCP_POOL.stop_idle_cleanup()

    if settings.run_cron:
        CRON_MANAGER.stop()
        logging.info("Cron stopped")

    await FileAnalysisService.stop_global_scheduler()
    logging.info("Code analysis scheduler stopped")
    await CodeLSPService.close_all()
    logging.info("LSP connections stopped")

    try:
        await close_db()

        if STORAGE_CONN and hasattr(STORAGE_CONN,"close"):
            try:
                await STORAGE_CONN.close()
            except Exception as e:
                logging.warning("Error while closing storage connection: %s",e)
        logging.info("Storage connection closed")

        if VECTOR_STORE_CONN and hasattr(VECTOR_STORE_CONN,"close"):
            try:
                await VECTOR_STORE_CONN.close()
            except Exception as e:
                logging.warning("Error while closing vector store connection: %s",e)
        logging.info("Vector store connection closed")

        if REDIS_CONN and hasattr(REDIS_CONN,"close"):
            try:
                await REDIS_CONN.close()
            except Exception as e:
                logging.warning("Error while closing Redis connection: %s",e)
        logging.info("Redis connection closed")
    except Exception as e:
        logging.error("Shutdown failed: %s",e)

    logging.info("Application shutting down")


async def _run_cli(args:argparse.Namespace)->None:
    await startup_event()
    try:
        runtime=CliRuntime(args)
        await runtime.run()
    finally:
        await shutdown_event()


def main()->None:
    setup_logging()
    parser=build_parser()
    args=parser.parse_args()
    if not args.command:
        args.command="interactive"
    asyncio.run(_run_cli(args))


if __name__=="__main__":
    main()
