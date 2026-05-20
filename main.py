# main.py
import uvloop
import asyncio
from src.engine import Engine

if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(Engine().run())
    except KeyboardInterrupt:
        print("Stopped")