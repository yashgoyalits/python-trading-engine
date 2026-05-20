import uvloop
import asyncio
import os
from src.engine import Engine

if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(Engine().run())
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        os._exit(0)