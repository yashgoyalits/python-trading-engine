import asyncio
import time
from src.core.shm_store import ShmStore
from src.infrastructure.shm_symbols import SymbolRegistry
from src.core.dtypes import MAX_SYMBOLS, MAX_TICKS_PER_SYMBOL


class Monitor:
    def __init__(self):
        self.shm     = ShmStore(create=False)
        self.symbols = SymbolRegistry()
        self.symbols.register("NSE:NIFTY50-INDEX")

        self.last_tick_seq = [0] * MAX_SYMBOLS
        self.tps           = [0.0] * MAX_SYMBOLS

    async def run(self):
        print("Starting Monitor (Press Ctrl+C to stop)...")

        while True:
            current_seqs = []
            for sym_name, sym_idx in self.symbols.all().items():
                if sym_idx is None:
                    continue

                c_seq = int(self.shm.ctrl[sym_idx]['tick_seq'])
                diff  = c_seq - self.last_tick_seq[sym_idx]
                self.tps[sym_idx]           = diff
                self.last_tick_seq[sym_idx] = c_seq

                widx  = int(self.shm.ctrl[sym_idx]['tick_widx'])
                l_idx = (widx - 1) % MAX_TICKS_PER_SYMBOL
                tick  = self.shm.ticks[sym_idx * MAX_TICKS_PER_SYMBOL + l_idx]

                current_seqs.append({
                    "symbol":      sym_name,
                    "ltp":         float(tick['ltp']),
                    "tps":         self.tps[sym_idx],
                    "total_ticks": c_seq,
                })

            self._display(current_seqs)
            await asyncio.sleep(1.0)

    def _display(self, data):
        print("\033[H\033[J")
        print(f"{'SYMBOL':<20} | {'LTP':<10} | {'TPS':<10} | {'TOTAL_TICKS':<15}")
        print("-" * 65)
        for d in data:
            print(f"{d['symbol']:<20} | {d['ltp']:<10.2f} | {d['tps']:<10} | {d['total_ticks']:<15}")

        o_ctrl = self.shm.order_ctrl[0]
        print(f"\nOrders Processed: {o_ctrl['seq']}")


if __name__ == "__main__":
    monitor = Monitor()
    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
    finally:
        monitor.shm.cleanup()