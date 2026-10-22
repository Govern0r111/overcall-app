# Synthetic generator changelog

- 1.0.1: Removed the legacy Mongo `_id` field from persisted log records so generated rows use the shared SQL `id` contract.
- 1.1.0: Added five user-approved adversarial positive patterns to measure missed cases beyond the current exact-match and threshold rules.
