import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overcall.hashing import normalize_endpoint  # noqa: E402
from overcall.synthetic import generate  # noqa: E402


def test_generator_is_seedable():
    logs_a, truth_a = generate(seed=3, days=1)
    logs_b, truth_b = generate(seed=3, days=1)
    a = [(log.endpoint, log.req_hash) for log in logs_a]
    b = [(log.endpoint, log.req_hash) for log in logs_b]
    assert a == b
    assert truth_a == truth_b


def test_endpoint_normalization():
    assert normalize_endpoint("/v1/customers/cus_Ab12CdEf34") == "/v1/customers/{id}"
    assert normalize_endpoint("/v1/setup_intents") == "/v1/setup_intents"
    assert normalize_endpoint("/v1/chat/completions") == "/v1/chat/completions"
