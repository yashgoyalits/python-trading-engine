# src/error_handling/retry.py
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception
from src.logger import log
from src.error_handling.exceptions import classify_exception
from src.error_handling.policies import RetryPolicy

def with_retry(policy: RetryPolicy, label: str | None = None):
    def decorator(fn):
        _label = label or fn.__qualname__

        def _before_sleep(retry_state):
            exc = retry_state.outcome.exception()
            log.warning(
                f"[RETRY] {_label} attempt {retry_state.attempt_number}/"
                f"{policy.max_attempts} failed: {exc} — retrying"
            )

        return retry(
            stop=stop_after_attempt(policy.max_attempts),
            wait=wait_exponential_jitter(initial=policy.base_delay, max=policy.max_delay),
            retry=retry_if_exception(classify_exception),
            before_sleep=_before_sleep,
            reraise=True,
        )(fn)

    return decorator
