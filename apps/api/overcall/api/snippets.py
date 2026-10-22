from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import Snippet

ROUTES_PATH = (
    Path(__file__).resolve().parents[4] / "contract" / "fixtures" / "proxy" / "routes.json"
)


@lru_cache(maxsize=1)
def load_routes() -> dict[str, Any]:
    return json.loads(ROUTES_PATH.read_text(encoding="utf-8"))


def route_prefix(provider: str) -> str:
    for route in load_routes()["routes"]:
        if route["provider"] == provider:
            return route["prefix"]
    raise KeyError(provider)


def proxy_base_url(public_base: str, provider: str) -> str:
    return f"{public_base.rstrip('/')}{route_prefix(provider)}"


def build_snippets(public_base: str, provider: str) -> list[Snippet]:
    routes = load_routes()
    header = routes["ingest_header"]
    key = routes["key_placeholder"]
    base = proxy_base_url(public_base, provider)
    if provider == "openai":
        return [
            Snippet(
                id="curl",
                label="curl",
                code=(
                    f"curl {base}/chat/completions \\\n"
                    '  -H "Authorization: Bearer $OPENAI_API_KEY" \\\n'
                    f'  -H "{header}: {key}" \\\n'
                    '  -H "Content-Type: application/json" \\\n'
                    '  -d \'{"model":"gpt-4o-mini",'
                    '"messages":[{"role":"user","content":"Hello"}]}\''
                ),
            ),
            Snippet(
                id="python",
                label="Python",
                code=(
                    "from openai import OpenAI\n\n"
                    "client = OpenAI(\n"
                    f'    base_url="{base}",\n'
                    f'    default_headers={{"{header}": "{key}"}},\n'
                    ")"
                ),
            ),
            Snippet(
                id="node",
                label="Node",
                code=(
                    'import OpenAI from "openai";\n\n'
                    "const client = new OpenAI({\n"
                    f'  baseURL: "{base}",\n'
                    f'  defaultHeaders: {{ "{header}": "{key}" }},\n'
                    "});"
                ),
            ),
        ]
    if provider == "stripe":
        stripe_root = base.removesuffix("/v1")
        return [
            Snippet(
                id="curl",
                label="curl",
                code=(
                    f"curl {base}/payment_intents \\\n"
                    "  -u $STRIPE_TEST_KEY: \\\n"
                    f'  -H "{header}: {key}" \\\n'
                    "  -d amount=2000 -d currency=usd"
                ),
            ),
            Snippet(
                id="python",
                label="Python",
                code=(
                    "import requests\nimport stripe\n\n"
                    "session = requests.Session()\n"
                    f'session.headers["{header}"] = "{key}"\n'
                    "stripe.default_http_client = stripe.RequestsClient(session=session)\n"
                    f'stripe.api_base = "{stripe_root}"'
                ),
            ),
            Snippet(
                id="node",
                label="Node",
                code=(
                    'import Stripe from "stripe";\n\n'
                    "const viaOvercall = (url, init) =>\n"
                    f'  fetch(String(url).replace("https://api.stripe.com", "{stripe_root}"), {{\n'
                    "    ...init,\n"
                    f'    headers: {{ ...init.headers, "{header}": "{key}" }},\n'
                    "  });\n\n"
                    "const stripe = new Stripe(process.env.STRIPE_TEST_KEY, {\n"
                    "  httpClient: Stripe.createFetchHttpClient(viaOvercall),\n"
                    "});"
                ),
            ),
        ]
    return []
