# Companion memory edition

This directory carries two deliberately separate memory classes.

## Inherited method pins

`cal-method-pins.jsonl` and `darin-method-pins.jsonl` contain genericized
operating knowledge. Every row is explicitly marked
`"inherited_from":"origin-studio"`. These are methods the companions inherit,
not events they claim to have lived.

Each companion receives the same four constitutional pins plus a role-filtered
set: build and verify for Cal; walk and decision for Darin. The edition stays
below the twelve-pin ceiling.

## Crew memories

The two `*-crew-memories.jsonl` files are intentionally empty until the manual
three-agent rehearsal has actually happened. Do not invent starter anecdotes.

After a real rehearsal, a curator may add a bounded row only when the event
resolves by timestamp against that rehearsal's own journal:

```json
{"timestamp":"<journal timestamp>","event_uid":"<journal event identifier>","summary":"<what this companion learned>","inherited_from":"origin-studio"}
```

The origin journal is build-time evidence and does not travel in a customer's
package. Set `TROPO_COMPANION_REHEARSAL_JOURNAL` to its path when running the
crew-memory gate. Method pins never participate in that event-resolution check.

Until the cognition walk and rehearsal are recorded, the empty crew partition
is an honest pending state, not evidence that the companions have worked
together.
