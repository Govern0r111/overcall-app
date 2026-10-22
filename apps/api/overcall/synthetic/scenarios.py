from datetime import timedelta


def _label(rule: str, role: str, pattern: str) -> tuple[str, str, str]:
    return rule, role, pattern


def inject_scenarios(generator, repeat: int) -> None:
    duplicate = "duplicate_calls"
    missing_cache = "missing_cache"
    retry = "retry_storm"
    oversized = "oversized_payload"
    unbatched = "unbatched_calls"
    token_bloat = "token_bloat"
    model_overuse = "model_overuse"

    for index in range(repeat):
        day = index % generator.days
        ts = generator.when(day)

        # Plausible misses: rapid resubmits, boundary repeats, and retries after failure.
        h = generator.hash_for(f"double-submit-{index}")
        generator.chat(ts, "gpt-4o-mini", 450, 80, h=h, caller="checkout")
        generator.chat(
            ts + timedelta(seconds=0.8),
            "gpt-4o-mini",
            450,
            80,
            h=h,
            caller="checkout",
            labels=[_label(duplicate, "positive", "double_submit")],
        )

        h = generator.hash_for(f"page-refresh-{index}")
        generator.chat(ts, "gpt-4o-mini", 380, 70, h=h, caller="support-chat")
        for attempt in range(1, 3):
            generator.chat(
                ts + timedelta(seconds=attempt),
                "gpt-4o-mini",
                380,
                70,
                h=h,
                caller="support-chat",
                labels=[_label(duplicate, "positive", "page_refresh_storm")],
            )

        h = generator.hash_for(f"duplicate-boundary-{index}")
        generator.chat(ts, "gpt-4o-mini", 520, 90, h=h)
        generator.chat(
            ts + timedelta(seconds=9.9),
            "gpt-4o-mini",
            520,
            90,
            h=h,
            labels=[_label(duplicate, "positive", "duplicate_calls_boundary_9_9s")],
        )

        h = generator.hash_for(f"duplicate-10-5-{index}")
        generator.chat(ts, "gpt-4o-mini", 520, 90, h=h)
        generator.chat(
            ts + timedelta(seconds=10.5),
            "gpt-4o-mini",
            520,
            90,
            h=h,
            labels=[_label(duplicate, "hard_negative", "same_payload_after_10_5s")],
        )

        h = generator.hash_for(f"rapid-different-{index}")
        generator.chat(ts, "gpt-4o-mini", 520, 90, h=h)
        generator.chat(
            ts + timedelta(seconds=0.5),
            "gpt-4o-mini",
            521,
            90,
            h=generator.hash_for(f"rapid-different-next-{index}"),
            labels=[_label(duplicate, "hard_negative", "different_payloads_rapidly")],
        )

        h = generator.hash_for(f"failed-then-success-{index}")
        generator.chat(ts, "gpt-4o-mini", 520, 90, status=500, h=h)
        generator.chat(
            ts + timedelta(seconds=0.5),
            "gpt-4o-mini",
            520,
            90,
            h=h,
            labels=[
                _label(duplicate, "hard_negative", "same_payload_after_failed_call"),
                _label(retry, "hard_negative", "only_two_attempts"),
            ],
        )

        # Repeated cacheable reads, including the inclusive 600-second boundary.
        path = f"/v1/customers/cus_synthetic_{index}"
        h = generator.hash_for(f"polling-{index}")
        for attempt in range(4):
            generator.log(
                ts + timedelta(seconds=attempt * 60),
                "stripe",
                "GET",
                path,
                h=h,
                caller="account-page",
                labels=(
                    [_label(missing_cache, "positive", "polling_without_cache")]
                    if attempt
                    else None
                ),
            )

        h = generator.hash_for(f"cache-boundary-{index}")
        generator.log(ts, "stripe", "GET", path, h=h)
        generator.log(
            ts + timedelta(seconds=600),
            "stripe",
            "GET",
            path,
            h=h,
            labels=[_label(missing_cache, "positive", "missing_cache_boundary_600s")],
        )

        h = generator.hash_for(f"cache-long-negative-{index}")
        generator.log(ts, "stripe", "GET", path, h=h)
        generator.log(
            ts + timedelta(seconds=601),
            "stripe",
            "GET",
            path,
            h=h,
            labels=[_label(missing_cache, "hard_negative", "same_get_after_long_window")],
        )

        h = generator.hash_for(f"chat-nondeterministic-{index}")
        generator.chat(ts, "gpt-4o-mini", 600, 100, h=h)
        generator.chat(
            ts + timedelta(seconds=30),
            "gpt-4o-mini",
            600,
            100,
            h=h,
            labels=[
                _label(missing_cache, "hard_negative", "non_deterministic_chat_repeat")
            ],
        )

        h = generator.hash_for(f"embedding-cache-{index}")
        for attempt in range(3):
            generator.embed(
                ts + timedelta(seconds=attempt * 45),
                100,
                h=h,
                caller="search-api",
                labels=(
                    [_label(missing_cache, "positive", "repeated_embedding")]
                    if attempt
                    else None
                ),
            )

        # Plausible miss: a minimum-length retry storm with no backoff.
        h = generator.hash_for(f"retry-storm-{index}")
        for attempt, status in enumerate((429, 429, 429, 200)):
            generator.chat(
                ts + timedelta(milliseconds=attempt * 250),
                "gpt-4o-mini",
                600,
                120,
                status=status,
                h=h,
                caller="completion-worker",
                labels=(
                    [
                        _label(retry, "positive", "no_backoff_retries"),
                        _label(retry, "positive", "retry_storm_minimum_attempts"),
                    ]
                    if attempt
                    else None
                ),
            )

        h = generator.hash_for(f"retry-exponential-{index}")
        at = ts
        for attempt, delay in enumerate((0, 1, 2, 4)):
            generator.chat(
                at + timedelta(seconds=delay),
                "gpt-4o-mini",
                600,
                120,
                status=200 if attempt == 3 else 429,
                h=h,
                labels=(
                    [_label(retry, "hard_negative", "exponential_backoff")]
                    if attempt
                    else None
                ),
            )

        h = generator.hash_for(f"stripe-idempotent-retry-{index}")
        for attempt, status in enumerate((429, 429, 200)):
            generator.log(
                ts + timedelta(seconds=attempt * 1.5),
                "stripe",
                "POST",
                "/v1/payment_intents",
                status=status,
                h=h,
                idem=True,
                caller="checkout",
                labels=(
                    [
                        _label(
                            retry,
                            "hard_negative",
                            "stripe_idempotent_retry_with_backoff",
                        )
                    ]
                    if attempt
                    else None
                ),
            )

        # Plausible miss: payload just over the configured size threshold.
        generator.chat(
            ts,
            "gpt-4o",
            55_000,
            250,
            req_size=200_001,
            caller="document-summarizer",
            labels=[
                _label(oversized, "positive", "giant_document_prompt"),
                _label(oversized, "positive", "oversized_payload_boundary_plus_one"),
            ],
        )
        generator.log(
            ts,
            "stripe",
            "GET",
            "/v1/events",
            resp_size=200_000,
            labels=[
                _label(oversized, "hard_negative", "payload_exactly_at_threshold")
            ],
        )
        generator.log(
            ts,
            "stripe",
            "GET",
            "/v1/events",
            resp_size=420_000,
            caller="billing-cron",
            labels=[_label(oversized, "positive", "large_event_list")],
        )

        # Every individual call is below the time threshold, with a batch equivalent.
        for attempt in range(5):
            generator.embed(
                ts + timedelta(milliseconds=attempt * 300),
                80,
                caller=f"embedding-loop-{index}",
                labels=(
                    [_label(unbatched, "positive", "loop_of_single_embeddings")]
                    if attempt
                    else None
                ),
            )
        for attempt in range(4):
            generator.embed(
                ts + timedelta(milliseconds=attempt * 250),
                80,
                caller=f"four-call-burst-{index}",
                labels=(
                    [_label(unbatched, "hard_negative", "four_call_burst")]
                    if attempt
                    else None
                ),
            )
        for attempt in range(5):
            generator.embed(
                ts + timedelta(seconds=attempt * 6),
                80,
                caller=f"slow-embedding-loop-{index}",
                labels=(
                    [_label(unbatched, "hard_negative", "five_calls_six_seconds_apart")]
                    if attempt
                    else None
                ),
            )

        context = generator.hash_for(f"system-context-{index}")
        for attempt in range(4):
            generator.chat(
                ts + timedelta(seconds=attempt * 30),
                "gpt-4o-mini",
                2_000,
                120,
                ctx=context,
                context_tokens=1_200,
                labels=(
                    [_label(token_bloat, "positive", "repeated_system_prompt")]
                    if attempt
                    else None
                ),
            )
        below_minimum_context = generator.hash_for(f"small-context-{index}")
        for attempt in range(3):
            generator.chat(
                ts + timedelta(seconds=attempt * 30),
                "gpt-4o-mini",
                900,
                100,
                ctx=below_minimum_context,
                context_tokens=900,
                labels=(
                    [
                        _label(
                            token_bloat,
                            "hard_negative",
                            "repeated_context_below_token_minimum",
                        )
                    ]
                    if attempt
                    else None
                ),
            )
        too_few_repeats = generator.hash_for(f"few-context-{index}")
        for attempt in range(2):
            generator.chat(
                ts + timedelta(seconds=attempt * 30),
                "gpt-4o-mini",
                2_000,
                100,
                ctx=too_few_repeats,
                context_tokens=1_300,
                labels=(
                    [
                        _label(
                            token_bloat,
                            "hard_negative",
                            "context_repeated_too_few_times",
                        )
                    ]
                    if attempt
                    else None
                ),
            )

        # Plausible miss: a high-cost model exactly at the small-task limits.
        for attempt in range(10):
            generator.chat(
                ts + timedelta(seconds=attempt * 2),
                "gpt-4o",
                800,
                300,
                caller="classifier-worker",
                labels=[
                    _label(model_overuse, "positive", "premium_model_for_tiny_task"),
                    _label(
                        model_overuse,
                        "positive",
                        "model_overuse_boundary_800_tokens",
                    ),
                ],
            )
        for attempt in range(10):
            generator.chat(
                ts + timedelta(seconds=attempt * 2),
                "gpt-4o",
                900,
                100,
                caller="long-prompt-worker",
                labels=(
                    [
                        _label(
                            model_overuse,
                            "hard_negative",
                            "premium_model_with_long_prompt",
                        )
                    ]
                    if attempt == 0
                    else None
                ),
            )
        for attempt in range(10):
            generator.chat(
                ts + timedelta(seconds=attempt * 2),
                "gpt-4o",
                400,
                80,
                caller="tool-using-worker",
                uses_tools=True,
                labels=(
                    [
                        _label(
                            model_overuse,
                            "hard_negative",
                            "premium_model_with_tools",
                        )
                    ]
                    if attempt == 0
                    else None
                ),
            )
