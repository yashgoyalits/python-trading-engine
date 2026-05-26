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
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        os._exit(0)