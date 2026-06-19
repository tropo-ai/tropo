# Contributing to Tropo

Thanks for helping build Tropo. Here is how it works, plainly.

## What to contribute

- **What you build with Tropo** — your own agents, capsules, and studio templates. This is the most valuable kind of contribution, and a dedicated showcase/examples repo is coming for it. For now, open a Discussion to share what you made, or propose an example via a pull request.
- **The core** — fixes, documentation, and improvements to the OS itself, in this repo, via pull request.

## How a change gets in (the loop)

1. Fork this repo.
2. Make your change in your fork.
3. Open a pull request that says what changed and why.
4. A maintainer reviews, may request changes, and merges. Your work is credited to you.

That fork, change, pull request, review, merge loop is the whole mechanic.

## Conventions

- Tropo is markdown-native. Governed files carry YAML frontmatter (a `uid`, a `type`, and relationships). When you edit a typed file, follow the rules for that type in `.tropo/capsules/`.
- Keep each pull request small and focused: one concern at a time.
- Run the structural validator before you submit (see `.tropo/toolbelt.md` for the command). A clean validate is the bar.
- Do not include secrets. Your environment and keys live outside the repo and should stay there.

## Good first contributions

Improving the quick-start, fixing a doc, or adding a small example agent or capsule all make great first pull requests. Look for issues labeled `good first issue`.

## Questions and conduct

Open a Discussion for questions and ideas. Be respectful and help newcomers; see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). For anything security-sensitive, see [SECURITY.md](SECURITY.md).

Your ambition has a studio. Let's build.
