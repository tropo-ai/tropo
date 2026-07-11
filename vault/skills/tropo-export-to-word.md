---
skill: export-to-word
name: export-to-word
type: how-to
purpose: Export a markdown document to a branded MindBridge Word (.docx) file using the correct template
when: When a user asks to export, publish, or download a document as Word / .docx
mode: both
uid: 19690406
status: active
owner: talos
created: 2026-05-31
modified: 2026-05-31
modified_by: talos-t11
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this when a user wants a markdown vault file or any markdown content exported as a Word document. The tool handles MindBridge branding automatically — logo, header, fonts, and footer — from the selected template. Two templates exist: internal (footer reads INTERNAL — CONFIDENTIAL) and external (footer reads MindBridge). Always present the template choice to the user before exporting.'
subsystem_hub:
  - 76bab75f
---

# Export to Word

Use this to convert any markdown content to a branded MindBridge `.docx` file. The output carries the MindBridge logo, styled headings, and a page-numbered footer — from a template the user selects.

---

## Steps

### 1. Discover available templates

```python
import sys
sys.path.insert(0, '.tropo/scripts')
from publish_targets.docx import list_templates

templates = list_templates()
# Returns: [{slug, label, audience, path}, ...]
```

Present the options to the user:

> "Which template would you like?
> - **Internal** — team briefings, strategy docs, working drafts not for external distribution *(footer: INTERNAL — CONFIDENTIAL)*
> - **External** — customer-facing, press, partner handoffs leaving MindBridge *(footer: MindBridge)*"

### 2. Read the markdown content

```python
with open(source_path) as f:
    md = f.read()
```

The source can be any vault file (`vault/files/<uid>.md`) or external-work markdown file. Strip frontmatter if needed — the tool handles it automatically.

### 3. Determine the output path

Default convention: `02-outbox/<slug>.docx`

If the user specifies a destination, use that. Keep the filename meaningful — `afo-manifesto-v0.1.docx`, not `output.docx`.

### 4. Call stage()

```python
from publish_targets.docx import stage

result = stage(
    extracted_content={"<filename>.md": md},
    pipeline_def={
        "title": "<Document Title>",           # Appears in header via TITLE field
        "output_path": "02-outbox/<slug>.docx",
        "template": "<path from list_templates()>",
    }
)
print("Saved to:", result.output_paths[0])
```

### 5. Open for the user

```bash
open 02-outbox/<slug>.docx
```

---

## Key facts

- **`title`** drives the header — set it to the document's display title, not the filename
- **Internal template** — `03-design/output-templates/ms-word-templates/mos-word-template-internal.dotx`
- **External template** — `03-design/output-templates/ms-word-templates/mos-word-template-external.dotx`
- **No server required** — runs entirely in Python; `python-docx` must be installed (`pip install python-docx`)
- **Styles** — headings H1/H2/H3, bold, bullets, numbered lists, code blocks all render; tables are flattened to text

---

## Example

```python
import sys
sys.path.insert(0, '.tropo/scripts')   # studio-root-relative — move-proof (this example runs from the studio root, like the relative open() below). Argus A97 self-heal 2026-06-05; replaces the hardcoded absolute path.
from publish_targets.docx import list_templates, stage

templates = list_templates()
# User selects internal
selected = next(t for t in templates if t['label'] == 'Internal')

with open('04-external-work/afo-manifesto/afo-manifesto-v0.1.md') as f:
    md = f.read()

stage(
    extracted_content={"afo-manifesto-v0.1.md": md},
    pipeline_def={
        "title": "Autonomous Financial Oversight — AFO Manifesto",
        "output_path": "02-outbox/afo-manifesto-v0.1.docx",
        "template": selected['path'],
    }
)
```

---

*export-to-word.skill.md | UID 19690406 | Talos T11 | 2026-05-31*
