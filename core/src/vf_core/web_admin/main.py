from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn
from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager
from vf_core.web_admin.api import system

from .api import config, plugins

"""Vessel Frame Admin server.

Exposes REST endpoints for configuration and plugin management and serves the
single-page admin UI.

Run via:
    uvicorn web_admin.main:app --host 127.0.0.1 --port 8000
"""


app = FastAPI(title="Vessel Frame Admin Panel")

# Mount API routes
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(plugins.router, prefix="/api/plugins", tags=["plugins"])
app.include_router(system.router, prefix="/api/system", tags=["system"])

# Serve static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Serve the index page when root requested"""
    return FileResponse(static_dir / "index.html")


async def start_admin_server(
    config_manager: ConfigManager,
    plugin_manager: PluginManager,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """
    Start the admin server.

    Attaches the core `ConfigManager` and `PluginManager` to `app.state` for use by
    API routes.

    Args:
        config_manager (ConfigManager): Shared configuration manager instance.
        plugin_manager (PluginManager): Shared plugin manager instance.
        host (str, optional): Host address to bind. Defaults to "127.0.0.1".
        port (int, optional): TCP port to listen on. Defaults to 8000.
    """
    app.state.config_manager = config_manager
    app.state.plugin_manager = plugin_manager

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    server.install_signal_handlers = False
    await server.serve()
