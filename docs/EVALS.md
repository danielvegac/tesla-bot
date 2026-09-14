# Evals and logs

## Structured log

Each agent turn appends one JSON line to `logs/agent.jsonl` (gitignored).

Kinds: `turn`, `tool`, `confirm`, `llm`.

No tokens or Authorization headers. Read with:

```bash
tail -n 20 logs/agent.jsonl
```

## Offline evals

Does not call Tesla or OpenRouter.

```bash
cd ~/Desktop/tesla-familia-bot
python3 -m evals.run
```

Four suites:

1. **intents** — `family_actions.classify` on the family phrases (flash, honk, lock, climate, wake).
2. **direct** — same phrases must hit `handle_direct`, record a FakeTesla write, and make **zero** LLM calls. `BoomLLM` explodes if the router regresses to Qwen.
3. **honesty** — asleep flash returns Tesla 500, not a canned refusal; stale `locked=true` still POSTs; climate stop + telemetry still ON is `ok=false`.
4. **tools** — agent tools: no invented battery while asleep; unlock still asks confirm.

Add phrases in `evals/cases.json` (`intents` + `direct`). Do not add live VIN calls here.
