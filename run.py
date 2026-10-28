import os

import uvicorn

from app.config.settings import APP_ENV


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    production = APP_ENV in {"production", "prod"}

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0" if production else "127.0.0.2",
        port=port,
        reload=not production,
    )
