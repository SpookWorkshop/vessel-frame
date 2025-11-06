from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn
from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager

from .api import config, plugins

app = FastAPI(title="Vessel Frame Admin Panel")

# Mount API routes
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(plugins.router, prefix="/api/plugins", tags=["plugins"])

# Serve static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(static_dir / "index.html")

# Run with:
# uvicorn web_admin.main:app --host 127.0.0.1 --port 8000
# or by calling this function
async def start_admin_server(config_manager: ConfigManager, plugin_manager: PluginManager, host: str = "127.0.0.1", port: int = 8000) -> None:
    app.state.config_manager = config_manager
    app.state.plugin_manager = plugin_manager

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    
    server.install_signal_handlers = False
    await server.serve()