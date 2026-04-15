import uvloop
import asyncio
from src.engine import main

if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")