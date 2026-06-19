#.tropo/system/ — System Agent Templates

Templates for agents that maintain the vault itself. Instance agents live in `system/` at vault root and inherit behavior from their template here via the phone-home pattern.

System agent templates are part of the kernel. Do not modify directly — they update when the framework updates.
