# src/error_handling/reconnect.py
import threading
import time
from typing import Callable
from tenacity import Retrying, stop_after_attempt, wait_exponential_jitter, RetryError
from src.logger import log
from src.error_handling.exceptions import ReconnectFailedError
from src.error_handling.policies import RetryPolicy

class ReconnectSupervisor:
    def __init__(
        self,
        name: str,
        reconnect_fn: Callable[[], None],
        is_connected_fn: Callable[[], bool],
        policy: RetryPolicy,
        on_exhausted: Callable[[], None] | None = None,
        grace_period: float = 2.0,
    ):
        self._name            = name
        self._reconnect_fn    = reconnect_fn
        self._is_connected_fn = is_connected_fn
        self._policy          = policy
        self._on_exhausted    = on_exhausted
        self._grace           = grace_period
        self._lock            = threading.Lock()
        self._active          = False   # ek waqt mein sirf ek reconnect cycle chale

    def trigger(self) -> None:
        """on_close se call karo — non-blocking hai."""
        with self._lock:
            if self._active:
                return    # already ek reconnect cycle chal raha hai, dobara mat lagao
            self._active = True

        threading.Thread(
            target=self._run, name=f"{self._name}_reconnect", daemon=True
        ).start()

    def _run(self) -> None:
        retryer = Retrying(
            stop=stop_after_attempt(self._policy.max_attempts),
            wait=wait_exponential_jitter(
                initial=self._policy.base_delay, max=self._policy.max_delay
            ),
            before_sleep=self._before_sleep,
            reraise=False,    # exhaust hone par tenacity.RetryError raise ho — niche pakdo
        )
        try:
            retryer(self._attempt_once)
            log.info(f"[{self._name}] Reconnect succeeded")
        except RetryError:
            log.error(
                f"[{self._name}] Reconnect exhausted after "
                f"{self._policy.max_attempts} attempts — giving up"
            )
            if self._on_exhausted:
                self._on_exhausted()
        finally:
            with self._lock:
                self._active = False

    def _attempt_once(self) -> None:
        if self._is_connected_fn():
            return
        self._reconnect_fn()
        time.sleep(self._grace)   # connect() khud thread spawn karta hai — grace period
        if not self._is_connected_fn():
            raise ReconnectFailedError(f"{self._name}: still not connected")

    def _before_sleep(self, retry_state) -> None:
        log.warning(
            f"[{self._name}] Reconnect attempt {retry_state.attempt_number}/"
            f"{self._policy.max_attempts} failed — retrying"
        )
