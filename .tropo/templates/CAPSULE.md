---
spec_version: 2
tier: capsule
folder_type: <type>
owner: <agent-or-person>
write_access: [<list>]
read_access: all
purpose: "<one-line description of what this folder is for>"
# Optional fields -- include only when overriding vault defaults or binding logic
# logic_binding: <agent-or-playbook>
# naming: <pattern>
# lifecycle: <string>
# package_type: <string>
---

# <Folder Name>

<One to three sentences describing this folder's purpose and what belongs here.>

<!-- 
 CAPSULE.md GENERATION NOTES (for concierge / migration playbook)
 
 This is the minimal CAPSULE.md template. When generating for a specific folder:
 
 1. Fill frontmatter from context:
 - folder_type: one of workspace, governed, registry, content, archive, sprint, package, system-agent
 - owner: the agent or person who owns this folder
 - write_access: who can write here (array of agent names / roles)
 - purpose: one-line description
 
 2. Write a short body describing the folder's purpose.
 
 3. Add Operating Logic section ONLY if the folder has specialized instructions
 (maintenance protocols, vocabulary rules, quality standards, workflow steps).
 Most folders don't need this -- vault defaults cover them.
 
 4. Add Override Declarations section ONLY if this folder deviates from STUDIO.md defaults
 (different naming convention, different lifecycle, broader write access, etc.)
 
 5. Add File Conventions section ONLY if this folder has specific file format requirements
 beyond the vault defaults.
 
 Keep it short. A simple workspace CAPSULE.md is 10 lines. A complex package
 CAPSULE.md might be 60 lines. If the body is longer than the file it governs,
 something is wrong.
-->
