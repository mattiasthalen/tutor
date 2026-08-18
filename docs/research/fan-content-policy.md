# Research: WotC Fan Content Policy and Scryfall notices

Ticket: [#13](https://github.com/mattiasthalen/tutor/issues/13) (child of the wayfinder map, [#2](https://github.com/mattiasthalen/tutor/issues/2)).

The map has already decided tutor ships a fan-project disclaimer. This note captures the mandated
texts, verbatim, from the two primary sources the ticket names, plus a proposed composite notice
and concrete placements for the spec ticket to adopt or amend.

All quotes below were fetched directly from the cited URLs on 2026-08-18. Anything not inside a
quotation block is my own summary or proposal, not mandated text.

## 1. Wizards of the Coast Fan Content Policy

Source: [Wizards of the Coast Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy),
page dated "Last Updated: November 15, 2017."

### 1.1 The mandated disclaimer

The policy requires a specific note, with a fill-in-the-blank title, wherever Fan Content is
shared:

> "Tell the Community it's unofficial. Make it clear that your Fan Content is not endorsed or
> sponsored by Wizards—i.e., unofficial. Please include a note with your Fan Content explaining
> that:
>
> '\[Title of your Fan Content] is unofficial Fan Content permitted under the Fan Content Policy.
> Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the
> Coast. ©Wizards of the Coast LLC.'"

With "tutor" as the title, the literal mandated text is:

> "tutor is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed
> by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the
> Coast LLC."

### 1.2 What counts as "Fan Content"

> "What kind of stuff does 'Fan Content' cover? Pretty much anything you create based on or
> incorporating our IP. Fan Content includes fan art, videos, podcasts, blogs, websites, streaming
> content, tattoos, altars to your cleric's deity, etc. The key is that it is your creation. It
> should go without saying, but Fan Content does not include the verbatim copying and reposting of
> Wizards' IP (e.g., freely distributing D&D® rules content or books, creating counterfeit/proxy
> Magic: The Gathering® cards, etc.), regardless of whether that content is distributed for free."

> "So, what exactly is Wizards IP? Wizards IP includes the cards, creatures, books, games,
> gameplay, pictures, stories, logos, animations, artwork, plots, locations, histories,
> characters, graphics, files, text, and other materials published by Wizards of the Coast."

Software isn't in the FAQ's example list, but Scryfall — itself Fan Content under this same policy
— explicitly reads the policy as covering "creating additional Magic software" (§2.1 below,
[scryfall.com/docs/api](https://scryfall.com/docs/api)). A Claude Code plugin that builds decks
from card data is squarely that: an original tool built on top of Wizards IP (card names, colors,
rules text pulled via a card database), not a repost of it. The FAQ's one explicit "don't" that
brushes against deckbuilding is the exclusion of "counterfeit/proxy Magic: The Gathering® cards" —
worth flagging now: if tutor ever grows a feature that exports print-ready card images (proxies),
that would fall outside Fan Content entirely and outside this policy's permission.

### 1.3 Free / no-paywall conditions

> "One word: F-R-E-E. You can use Wizards' IP (except for the restrictions listed in #3) to make
> Fan Content that you share with the community for free. Free means FREE:
>
> You can't require payments, surveys, downloads, subscriptions, or email registration to access
> your Fan Content;
>
> You can't sell or license your Fan Content to any third parties for any type of compensation;
> and
>
> Your Fan Content must be free for others (including Wizards) to view, access, share, and use
> without paying you anything, obtaining your approval, or giving you credit.
>
> You can, however, subsidize your Fan Content by taking advantage of sponsorships, ad revenue, and
> donations—so long as it doesn't interfere with the Community's access to your Fan Content."

Practical read for tutor: the plugin (and its marketplace listing) must be installable and usable
at no cost, with no signup/paywall gate, for this policy's permission to apply at all. This is a
hard constraint on however the marketplace/distribution decision lands, not just a wording
question.

### 1.4 Trademark / name-use rules

> "Don't hurt Wizards. We ask that you refrain from doing any of the following:
>
> Don't use Wizards' logos and trademarks. We've included a list of our most frequently
> asked-about trademarks in the FAQ;
>
> Don't mess with the legal notices in our stuff. If the Wizards IP you are incorporating into
> your Fan Content already has copyright notices, logos, trademarks, or other notices existing
> within it, don't remove them;
>
> Don't use Wizards' IP in other games. This includes your own or other people's games or game
> components (e.g., rule books, tokens, figures), regardless of whether it is distributed for
> free;
>
> Don't use Wizards' Video or Music in your Fan Content. […] use of our videos and music are
> governed by contracts with third parties. Please don't use any of our video or music content,
> unless you're embedding a video from an authorized third-party's website (e.g., Twitch or
> YouTube)."

FAQ, on logos specifically:

> "Can I use all of Wizards' IP? Unfortunately, no. You cannot incorporate Wizards patents, game
> mechanics (unless your Fan Content is created under the D&D Open Game License), logos, or
> trademarks into your Fan Content without our prior written permission."

> "May I put a logo on a t-shirt or a hat? A: Nope. Sorry, you would need permission from us for
> that. You may not incorporate any Wizards of the Coast logos and trademarks in your Fan Content
> without our prior, written consent."

The page's trademark list (referenced above as "the FAQ") is rendered as a block of logo images
with empty `alt` text, not as a text list, so it can't be quoted verbatim; the image filenames
visible in the page markup cover the current and legacy Magic: The Gathering logo, the Magic: The
Gathering Arena logo, the current and legacy Dungeons & Dragons logos, the D&D Beyond/DMsGuild
logo, and logos for Avalon Hill, Duel Masters, Betrayal at House on the Hill, and Axis & Allies.
None of these are things tutor has any reason to reproduce — the practical rule for tutor is: text
references to card names, set names, and "Magic: The Gathering" as a plain description of the game
are fine (that's how the mandated disclaimer itself refers to Wizards and the policy allows this
throughout its own FAQ), but no Wizards logo/wordmark graphic goes in the plugin's icon, README
badges, or marketplace listing art without permission.

### 1.5 Relationship to Wizards' other legal terms

> "Follow the law of the land. […] In addition to this Policy, your use of any Wizards' IP must
> also comply with Wizards' Terms of Use and Code of Conduct (together, the 'Wizards Terms'). If
> there's a conflict between anything in this Policy and the Wizards Terms, the Wizards Terms
> win."

I did not fetch the separate Wizards Terms of Use/Code of Conduct pages — out of scope for this
ticket's four required elements (disclaimer wording, Fan Content definition, free conditions,
trademark rules), all of which live on the Fan Content Policy page itself. Flagging their
existence here in case the spec ticket wants a follow-up research ticket.

## 2. Scryfall API documentation and Terms of Service

Sources: [scryfall.com/docs/api](https://scryfall.com/docs/api) ("Use of Scryfall Data and
Images" section) and [scryfall.com/docs/terms](https://scryfall.com/docs/terms) (Terms of
Service). Both are Scryfall's own current pages; neither carries a visible "last updated" date.

### 2.1 Framing: Scryfall data usage is Fan-Content-Policy-scoped

> "As part of the Wizards of the Coast Fan Content Policy, Scryfall provides our card data and
> image database free of charge for the primary purpose of creating additional Magic software,
> performing research, or creating community content (such as videos, streams, podcasts, etc.)
> about Magic and related products."

### 2.2 Non-endorsement wording

> "You may not use Scryfall logos or use the Scryfall name in a way that implies Scryfall has
> endorsed you, your work, or your product."

Unlike Wizards, Scryfall does not hand consumers a fill-in-the-blank notice string — this is a
behavioral rule (don't imply endorsement), not a mandated sentence. A plain non-endorsement
statement (drafted below in §3) satisfies it; nothing more specific is "mandated" text to quote.

### 2.3 No-paywall condition on Scryfall data

> "You may not 'paywall' access to Scryfall data. You may not require anyone to make payments,
> take surveys, agree to subscriptions, rate your content, join chat servers, or follow channels
> in exchange for access to Scryfall data. If you have an account system, end-users should be able
> to access card data anonymously or with free accounts."

This mirrors and reinforces the Fan Content Policy's own free/no-paywall condition (§1.3) — two
independent primary sources landing on the same constraint for tutor.

### 2.4 Things you may not imply / may not do with the data

> "You may not use Scryfall data to create new games, or to imply the information and images are
> from any other game besides Magic: The Gathering."

> "You may not simply repackage, republish, or proxy Scryfall data. Your software must create
> additional value for end-users."

Read together with §1.2's proxy-card exclusion, this is a second, independent source telling tutor
not to become a bare card-data repost — deckbuilding logic on top of the data is exactly the
"additional value" the rule asks for.

### 2.5 Image attribution rules

> "When using images from Scryfall, you must adhere to the following guidelines:
>
> Do not cover, crop, or clip off the copyright or artist name on card images.
>
> Do not distort, skew, or stretch card images.
>
> Do not blur, sharpen, desaturate, or color-shift card images.
>
> Do not add your own watermarks, stamps, or logos to card images.
>
> Do not place card images in a way that implies someone other than Wizards of the Coast created
> the card or that it is from another game besides Magic: The Gathering.
>
> When using the art_crop, list the artist name and copyright elsewhere in the same interface
> presenting the art crop, or use the full card image elsewhere in the same interface. Users
> should be able to identify the artist and source of the image somehow."

Only relevant if/when tutor renders card images (e.g., an art crop in a generated deck sheet); not
relevant to a text-only decklist.

### 2.6 Price-data and legality caveats

These are in the Terms of Service, not the API docs page, but they are Scryfall's own mandated
caveats on the two data fields a deckbuilder is most likely to surface:

> "Price data is for informational purposes only. Scryfall may include information about the
> price of third-party products or cards. Absolutely no guarantees are made for this information.
> See stores for final prices."

> "Card legality is provided for informational purposes only. Scryfall may include information
> about the tournament legality of cards. Absolutely no guarantees are made for this information.
> Please contact a local DCI Judge or Wizards of the Coast customer service for help with
> evaluating your deck for sanctioned events."

(Source: [scryfall.com/docs/terms](https://scryfall.com/docs/terms), "Limitation of Liability"
section.)

### 2.7 Enforcement

> "Repeated mishandling or misrepresentation of data or images in your project may result in
> Scryfall restricting or blocking your API access."

### 2.8 Required technical header (not a notice, but a compliance condition)

> "All HTTP requests to api.scryfall.com must include a User-Agent header and an Accept header.
> Your User-Agent header must be accurate to your usage context. If you are running a script or
> app, the header should be the name of your application, such as MTGExampleApp/1.0 or the current
> relevant version. Do not allow HTTP libraries to choose the header for you."

Noted for whoever implements the Scryfall client: tutor's `User-Agent` should identify tutor, not
default to the HTTP library's string. This is an implementation detail, not disclaimer wording,
but it's a documented condition of API access and belongs in the same compliance checklist.

## 3. Proposed composite notice (not mandated text — drafted from the quotes above)

Two lengths, both built only from the obligations quoted above.

**Full form** (README, a dedicated notice file):

> tutor is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by
> Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the
> Coast LLC.
>
> Card data and card images, where used, are retrieved via the Scryfall API. This project is not
> produced by, affiliated with, or endorsed by Scryfall. Card prices and legality information are
> informational only, sourced from Scryfall's data, not guaranteed accurate or current, and are no
> substitute for checking with a store or a certified judge before an event.

**Short form** (plugin metadata, deck-artifact footers):

> tutor is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by
> Wizards of the Coast or Scryfall.

The first sentence of the short form is the mandated WotC text verbatim (§1.1) with the title
filled in; everything after "Wizards" is my addition to also cover Scryfall's non-endorsement rule
(§2.2) in the same breath, since both notices are about non-endorsement and tutor is subject to
both. If the spec ticket wants the Scryfall clause kept fully separate from the word-for-word WotC
sentence, split it back into two sentences — nothing here forces them to merge.

## 4. Proposed placements in this repo

Checked against the actual plugin manifest schema
([code.claude.com/docs/en/plugins-reference](https://code.claude.com/docs/en/plugins-reference),
fetched 2026-08-18): `.claude-plugin/plugin.json` has exactly these optional metadata fields —
`displayName`, `version`, `description`, `author`, `homepage`, `repository`, `license`, `keywords`,
`metadata`, `defaultEnabled`, `$schema` — plus component-path and advanced fields unrelated to
legal text. There is no dedicated license-notice, disclaimer, or README field; the reference page
says so explicitly: "The manifest has no built-in README or legal notices field—documentation
should be maintained externally or linked via `homepage`." That shapes the placements below: the
full notice has to live in a real doc, with metadata fields pointing at it.

1. **README.md** — add a short "Legal" or "Disclaimer" section (top-of-file, near the badges, or a
   final section before any footer/license line — either is conventional; this repo's README is
   currently just a title and one-line description, so there's no existing convention to match).
   Put the **full form** notice from §3 there. This is the canonical, human-facing copy.

2. **A new `NOTICE.md`** (or `DISCLAIMER.md`) at repo root — holds the full form notice as the
   single source of truth, so the same text isn't retyped in three places. README's Legal section
   can be this file's content directly, or a short pointer to it — spec's call. Given there's no
   `license`/legal field in the manifest, this file (or the README section) is the only place the
   complete, accurate text has to exist; everything else can point at it.

3. **`.claude-plugin/plugin.json`** —
   - `description`: keep it short, but work "unofficial Fan Content" or "fan project" into it so
     the notice is visible in the `/plugin` picker without opening any file, e.g. `"Unofficial
     Magic: The Gathering deckbuilding — fan project, not affiliated with Wizards of the Coast."`
   - `homepage`: point at the README's Legal section (or `NOTICE.md`) so the full mandated text is
     one click away from the manifest.
   - Do not put legal text in `license` — that field is for the software license identifier (e.g.
     `MIT`), a different concern from the Fan Content disclaimer.

4. **`.claude-plugin/marketplace.json`** — the marketplace entry can repeat or override
   `description`/`homepage` per plugin
   ([code.claude.com/docs/en/plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)).
   Same short-form `description` and `homepage` pointer as plugin.json, so the disclaimer is
   visible at the marketplace-browsing step too, before install.

5. **Generated deck artifacts** — whatever tutor emits as a deck (Markdown deck sheet, exported
   decklist, session summary) should carry the **short form** notice from §3 as a trailing
   footer/line, plus — only on artifacts that show prices or legality — a one-line caveat drawn
   from §2.6, e.g. "Prices and legality shown are informational, sourced from Scryfall, and not
   guaranteed — verify before an event." Exact artifact shape is explicitly "not yet specified" on
   the map (deck-test artifact shape), so this is a placement rule for whatever format is chosen,
   not a file path.

6. **Card images, if ever rendered** — apply §2.5's rules at the point images are composed
   (don't crop the artist/copyright, keep artist credit visible in the same view). No repo location
   to point at yet since no image-rendering feature exists.

## 5. Open items for the spec ticket

- Confirm tutor actually calls the Scryfall API for card data (this ticket assumes so, per the
  map's mention of "Scryfall's notices" and the ManaBox-export domain, but the data-source decision
  itself isn't recorded on the map yet).
- Decide where the merged vs. split notice (§3) lands — one sentence covering both WotC and
  Scryfall, or two.
- Decide README section placement (top vs. bottom) — no existing repo convention to defer to.
- Confirm the marketplace/plugin distribution path keeps tutor free with no install gate, per
  §1.3/§2.3 — a hosting or paid-tier decision elsewhere on the map could conflict with this
  policy's condition for permission to apply at all.

## Sources

- Wizards of the Coast, [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy) — "Last Updated: November 15, 2017." Fetched 2026-08-18.
- Scryfall, [REST API Documentation](https://scryfall.com/docs/api), "Use of Scryfall Data and Images" section. Fetched 2026-08-18.
- Scryfall, [Terms of Service](https://scryfall.com/docs/terms), "Limitation of Liability" section. Fetched 2026-08-18.
- Anthropic, [Plugins reference](https://code.claude.com/docs/en/plugins-reference) — plugin.json field list. Fetched 2026-08-18.
- Anthropic, [Create and distribute a plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) — marketplace.json field list. Fetched 2026-08-18.
