---
type: agent-activation-pointer
agent: "{{slug}}"
role: "{{role}}"
display_name: "{{display_name}}"
generation_prefix: "{{generation_prefix}}"
agent_uid: "{{agent_uid}}"
party_uid: "{{party_uid}}"
agent_root_uid: "{{agent_root_uid}}"
created: "{{created}}"
generated_by: tropo-genesis-companions
---

# {{display_name}} — Activation

You are **{{display_name}}**, the Studio's {{role_lower}}. Your canonical
identity, charter, soul, boot extension, and current status are in
`vault/agents/{{agent_uid}}.md`.

Resolve the Studio root from this file at
`agents/{{slug}}/{{slug}}-activation.md`, then execute
`.tropo/playbooks/agent-activation.playbook.md`. That kernel pointer routes to
the canonical activation playbook carried by this Studio.

If the per-Studio boot derivations are absent, that is expected on a fresh
extraction. Continue through the canonical playbook; do not treat their absence
as a broken boot.
