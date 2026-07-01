import asyncio

from src.config import load
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_SYMBOLS, MAX_TICKS_PER_SYMBOL


class Monitor:
    def __init__(self):
        cfg = load()

        self.shm = ShmStore(
            timeframes=cfg["timeframes"],
            create=False,
        )

        self.last_tick_seq = [0] * MAX_SYMBOLS

    async def run(self):
        print("Starting Monitor (Ctrl+C to stop)")
        while True:
            self.display()
            await asyncio.sleep(1)

    def display(self):
        print("\033[H\033[J", end="")

        total_tps = 0
        total_ticks = 0
        active_slots = 0

        for sym_idx in range(MAX_SYMBOLS):
            ctrl = self.shm.ctrl[sym_idx]

            tick_seq = int(ctrl["tick_seq"])
            if tick_seq == 0:
                continue

            active_slots += 1

            tps = tick_seq - self.last_tick_seq[sym_idx]
            self.last_tick_seq[sym_idx] = tick_seq

            total_tps += tps
            total_ticks += tick_seq

        active_trades = sum(
            1 for trade in self.shm.trades
            if trade["active"]
        )

        order_ctrl = self.shm.order_ctrl[0]

        print(f"Active Slots     : {active_slots}")
        print(f"Total TPS        : {total_tps}")
        print(f"Total Tick Count : {total_ticks}")
        print(f"Active Trades    : {active_trades}")
        print(f"Orders Written   : {int(order_ctrl['widx'])}")
        print(f"Order Seq        : {int(order_ctrl['seq'])}")

        print()
        print("Candles")
        print("-" * 30)

        for tf, tf_idx in self.shm.tf_map.items():
            total = 0

            for sym_idx in range(MAX_SYMBOLS):
                if self.shm.ctrl[sym_idx]["tick_seq"] == 0:
                    continue

                total += int(
                    self.shm.ctrl[sym_idx]["tf_seq"][tf_idx]
                )

            print(f"{tf:>5}s : {total}")

    def close(self):
        self.shm.cleanup()


if __name__ == "__main__":
    monitor = Monitor()
    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        monitor.close()