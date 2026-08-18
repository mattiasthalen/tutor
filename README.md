# tutor

A Claude Code plugin that builds Magic: The Gathering decks from the cards you
actually own: settle a Brief, build until the deck's Checks run green, then get
an honest Review.

This repository is both the plugin and its marketplace: the marketplace
catalog's single entry points back at this repo, and one pinned version in the
plugin manifest is the sole version authority.

## Install

In any Claude Code session:

```
/plugin marketplace add mattiasthalen/tutor
/plugin install tutor@tutor
```

Every tutor command lives under the `/tutor:*` namespace. Verify the install
responds:

```
/tutor:hello
```

## Update

A release is a version bump to the plugin manifest in this repository —
nothing ships until that number changes. Auto-update is off by default for
self-hosted marketplaces, so either:

- enable auto-update for the `tutor` marketplace in `/plugin`, or
- update manually: run `/plugin marketplace update`, then `/plugin update tutor`.

## Releasing

Releases are cut with `scripts/release`, which bumps the pinned version,
mirrors it into every skill, drafts the [CHANGELOG.md](CHANGELOG.md) entry,
validates, and tags `tutor--v{version}`. See
[docs/releasing.md](docs/releasing.md) for the flow and for what MAJOR, MINOR,
and PATCH mean for prompt-ware.

## Legal

tutor is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Card data comes from the Scryfall API. tutor is not produced by, endorsed by,
or affiliated with Scryfall; card legality and any price information derived
from Scryfall data are informational only, never guarantees.

tutor is free and unpaywalled — a condition of both the Wizards of the Coast
Fan Content Policy and the Scryfall API guidelines. The full composite notice
lives in [NOTICE](NOTICE).
