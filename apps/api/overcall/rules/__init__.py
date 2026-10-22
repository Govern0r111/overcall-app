from .duplicate_calls import DuplicateCalls
from .missing_cache import MissingCache
from .model_overuse import ModelOveruse
from .oversized_payload import OversizedPayload
from .retry_storm import RetryStorm
from .token_bloat import TokenBloat
from .unbatched_calls import UnbatchedCalls

RULES = [DuplicateCalls(), MissingCache(), RetryStorm(), OversizedPayload(), UnbatchedCalls(), TokenBloat(), ModelOveruse()]
RULES_BY_ID = {r.id: r for r in RULES}
