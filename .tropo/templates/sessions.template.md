# [Agent Name] — Session Log

*Append-only. Each session adds one row. This is your lightweight identity and activity ledger.*

---

| Session | Date | Key Contribution |
|---------|------|------------------|

---

## How This Works

1. **At boot:** Read this file. Your session number = last row's Session + 1.
2. **At session end:** Append your row with date and key contribution (one line).
3. **Only you write here.** This is your self-maintained record.

## Why This Exists

Memory files capture rich context. This log captures the timeline — when you were active and what you did, at a glance. It's also how you know your session number without counting.

For agents with generational continuity (successor replaces predecessor), the log also tracks generation boundaries. Add a note like "G2 begins" when a new generation starts.
