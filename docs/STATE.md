# Agent session state

This bot does not use LangGraph. State lives in one Python object per Telegram chat.

## Fields

| Field | Meaning |
|---|---|
| `vehicle` | last `online` / `asleep` from Fleet |
| `pending_write` | unlock waiting for sí |
| `pending_nav` | destination waiting for mándalo after *alcanza* |
| `resume_after_wake` | lock/climate asked while asleep |
| `last_nav` | last destination Tesla accepted (`result: true`) |
| `last_nav_at` | unix time of that accept |

## Why not LangGraph

LangGraph is a graph of LLM nodes with checkpointing. Useful when an agent has 15 tools, branches, and human-in-the-loop across hours. Here the branches are four ifs. A graph library would hide the same bugs (`confirmed=True` from the model, wake without nav) behind more files.
