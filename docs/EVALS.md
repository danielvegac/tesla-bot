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

Covers wake phrases, confirm/deny, asleep read without battery, unlock blocked until confirm.

Add cases in `evals/cases.json`.
