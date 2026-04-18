# Configuration

## Environment Variables

See `.env.example` in `kaia/` for the full list. Key settings:

- `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` — required
- `CLAUDE_MODEL`, `CLAUDE_MAX_TOKENS`, `GROQ_API_KEY` — AI configuration
- `ALLOWED_TELEGRAM_IDS` — comma-separated whitelist
- `DEFAULT_TIMEZONE=Asia/Manila`, `DEFAULT_CURRENCY=PHP`
- `MAX_CONVERSATION_HISTORY=20` — message history window
- `INTENT_CONFIDENCE_THRESHOLD=0.6` — intent detection fallback threshold
- `FORUM_MODE_ENABLED=true` — enable Telegram Forum Topics routing (CH-1.1). Set to `false` to keep DM-only behaviour even in forum groups.

---

## Channel System Constants — `kaia/config/constants.py`

### Channel IDs

```python
CHANNEL_GENERAL = "general"
CHANNEL_HEVN = "hevn"
CHANNEL_KAZUKI = "kazuki"
CHANNEL_AKABANE = "akabane"
CHANNEL_MAKUBEX = "makubex"

ALL_CHANNELS = [CHANNEL_GENERAL, CHANNEL_HEVN, CHANNEL_KAZUKI, CHANNEL_AKABANE, CHANNEL_MAKUBEX]
```

### Channel Emojis

```python
CHANNEL_EMOJIS = {
    "general": "👑",
    "hevn":    "💰",
    "kazuki":  "📈",
    "akabane": "⚔️",
    "makubex": "🔧",
}
```

### Required Knowledge

`CHANNEL_REQUIRED_KNOWLEDGE` drives the knowledge gap detection for each expert channel. Format:

```python
CHANNEL_REQUIRED_KNOWLEDGE: dict[str, list[tuple[str, str, int, str]]] = {
    "hevn": [
        # (category, key, priority, question_text)
        ("income_info", "monthly_income", 1, "What's your monthly income?"),
        ("debt_info", "active_debts", 1, "Do you have any active loans or credit card debt?"),
        ...
    ],
    ...
}
```

- **Priority 1** = ask first (critical baseline knowledge)
- **Priority 2** = ask next (important context)
- **Priority 3** = ask later (nice-to-have details)

The expert system picks the single highest-priority missing item and injects a prompt instruction to weave ONE question about it into the response naturally. Never more than one question per response.

Hevn has 10 required knowledge items covering income, debts, savings, insurance, goals, risk, retirement, and dependents.
Kazuki has 7 items covering portfolio, experience, budget, time horizon, preferences, platforms, history.
Akabane has 7 items covering exchange, capital, risk-per-trade, experience, pairs, style, loss limits.
MakubeX has 6 items covering projects, stack, skills, learning goals, work context, dev environment.

### Adjusting Required Knowledge

To add a knowledge slot for a channel: add a tuple to the list. The system auto-derives the knowledge completeness score from this list (`len(known) / len(required) * 100`).

---

## Expert Keyword Matching — `kaia/core/expert_detector.py`

`_EXPERT_KEYWORDS` maps each channel to a keyword list. When KAIA handles a message via the `chat` skill, these keywords are matched against the user message + response. 2+ matches triggers a suggestion.

To tune: add/remove keywords in `_EXPERT_KEYWORDS` per channel. To prevent repeated nagging, the detector tracks per-user suggestion history in memory (resets on bot restart).
