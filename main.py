import asyncio
import os
import uvloop

from src.bootstrap import bootstrap, BootstrapError
from src.engine import Engine, EngineStartupError

if __name__ == "__main__":
    uvloop.install()

    try:
        bootstrap()
        asyncio.run(Engine().run())

    except BootstrapError as e:
        print(f"[BOOTSTRAP FAILED] {e}")

    except EngineStartupError as e:
        print(f"[STARTUP FAILED] {e}")

    except KeyboardInterrupt:
        print("Stopped")

    except Exception:
        import traceback
        traceback.print_exc()

    finally:
        os._exit(0)