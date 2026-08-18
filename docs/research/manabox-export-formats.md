# ManaBox export formats — collection and deck

Research for issue #3 (child of the wayfinder map, issue #2). ManaBox is the mobile MTG
collection-scanner app at [manabox.app](https://manabox.app). The question this answers: what
exactly a ManaBox export contains, in each of its variants, and what affects parsing
reliability. A later decision — how the tutor plugin ingests a collection — waits on this.

Researched 2026-08-18 against ManaBox's own site first, with corroboration from import docs
and issue trackers of tools that consume ManaBox exports (Moxfield, Archidekt, deckstats-adjacent
tools, MythicHub, Mana Pool, and a couple of purpose-built ManaBox CSV converters).

## Confidence key

- **Primary** — stated on manabox.app's own guides/FAQ pages.
- **Secondary (corroborated)** — stated independently by two or more non-ManaBox sources, or
  by one non-ManaBox source plus a real-world artifact (e.g. an error message quoting the
  literal value) that confirms it.
- **Secondary (single source)** — stated by exactly one non-ManaBox source, not independently
  checked elsewhere.
- **Unconfirmed** — searched for, not found anywhere. Flagged as an open question rather than
  guessed at.

## TL;DR for the ingestion decision

- ManaBox has two export surfaces: a **collection/binder CSV** and a **deck text file**.
  There is no deck CSV — decks only export as text, or as a shareable link. **[Primary]**
- The collection CSV's own "supported columns" list (framed for import, but export uses the
  same vocabulary) is: Card name, Set code/Set name, Quantity, Foil, Card number, Language,
  Condition, Purchase price, Purchase currency, Misprint, Altered, Scryfall ID. A real exported
  file carries more columns than that list names — Rarity, an internal ManaBox ID, Set Name as
  its own column, and the binder/list name are also present. See §1.2–§1.3. **[Primary +
  Secondary corroborated]**
- Card name + (Set code or Set name) is the minimum required identity for a row; **a Scryfall
  ID alone can substitute for all three**. **[Primary]**
- "Purchase price" is the user's recorded acquisition cost, not a live market price — if left
  unedited at add-time, ManaBox fills it with that card's price on the day it was added.
  **[Primary]**
- The deck text format is the MTGA-style `<qty> <name> (<set>) <collector number>` line format;
  set and collector number are optional. **[Primary]**
- Real, literal example of an exported collection CSV row (comma-delimited, `.` decimal
  separator): see §1.3. **[Secondary, single source, but a direct literal quote]**
- Known parsing gotchas from other tools' issue trackers: blank/alternating lines inside the
  CSV, a Condition column whose exact literal casing is disputed between sources, Language
  codes that don't map cleanly onto Scryfall's own language codes (especially Chinese
  variants), and comma-containing card names that require real CSV quote-handling rather than
  a naive split on commas. See §4.
- Character encoding, decimal-separator locale sensitivity, and BOM presence are **not
  documented anywhere I could find** — see §5 for what's confirmed vs. still open.

---

## 1. Collection export (CSV)

### 1.1 How to export

From the ManaBox app: "You can export a CSV of the whole collection from the top right menu in
the collection tab. The exported file will include all card properties as well as the
binder/list name. You can also export a single binder/list from the top right menu within the
respective binder/list screen."
Source: [Import and export the collection](https://manabox.app/guides/collection/import-export/)
(manabox.app guide). **[Primary]**

So there are two export scopes — the whole collection, or a single binder/list — and both are
CSV. There is no separate "deck-shaped" collection export; collections are always CSV.

### 1.2 Columns ManaBox itself documents ("Supported columns")

ManaBox's collection import/export guide lists these as the columns the CSV format
understands, under a section literally titled "Supported columns" (this list is written from
the *import* side, i.e. what a CSV needs to contain to be accepted, but the guide is explicit
that export "will include all card properties", so this is the same column vocabulary used on
export):

- Card name (**required**)
- Set code / Set name (**required**)
- Quantity
- Foil
- Card number
- Language
- Condition
- Purchase price
- Purchase currency
- Misprint
- Altered
- Scryfall ID

Verbatim from the guide: "The app needs to know some way of distinguishing different versions
of the same card, so, as a minimum the following columns are required: the 'card name' and
either the 'set name' or the 'set code'. The set names and codes supported are the same ones
from Scryfall, so refer there if you are creating the CSV yourself. Alternatively, if you have
a 'Scryfall ID', it can be used as a replacement for the card name and set name/code required
information."
Source: [Import and export the collection](https://manabox.app/guides/collection/import-export/). **[Primary]**

Practical implication for a downstream parser: Scryfall ID is the most reliable join key when
present, since it sidesteps set-code/set-name naming mismatches entirely (the guide calls out
"different naming convention with the set names" as the most common import failure).

### 1.3 The actual export header (real file, not just the "supported" list)

The "Supported columns" list above is a functional description, not a literal header dump.
Two independent secondary sources give the literal header row of a real exported CSV, and they
agree with each other and add three columns the primary doc doesn't name individually (Set
Name as its own column, Rarity, and an internal ManaBox ID):

```
Name,Set code,Set name,Collector number,Foil,Rarity,Quantity,ManaBox ID,Scryfall ID,Purchase price,Misprint,Altered,Condition,Language,Purchase price currency
```

- A ManaBox user posted this exact header (formatted with `|` separators for readability in
  their forum post, not necessarily the literal delimiter — see §5.1) while troubleshooting a
  TappedOut import:
  "My CSV headers from Manabox are as follows: |Name|Set Code|Set Name|Collector
  Number|Foil|Rarity|Quantity|ManaBox ID|Scryfall ID|Purchase Price|Misprint|Altered|Condition|Language|Purchase
  Price Currency|"
  Source: [Importing CSV from Manabox? — TappedOut forum](https://tappedout.net/mtg-forum/tappedout/importing-csv-from-manabox/). **[Secondary, single first-hand source]**
- A GitHub issue against a ManaBox↔Moxfield CSV conversion tool pastes what it calls a ManaBox
  CSV row with the same 15 columns, comma-delimited, plus one full example data row:

  ```
  Name,Set code,Set name,Collector number,Foil,Rarity,Quantity,ManaBox ID,Scryfall ID,Purchase price,Misprint,Altered,Condition,Language,Purchase price currency
  Dawn of a New Age,LTR,The Lord of the Rings: Tales of Middle-earth,5,normal,mythic,1,83505,cb966ee6-bf1b-4bb6-9277-8de6f3918ae2,1.84,false,false,near_mint,ja,USD
  ```

  Source: [StepKie/MtgCsvHelper issue #26](https://github.com/StepKie/MtgCsvHelper/issues/26). **[Secondary, single source]**
- A ManaBox→Archidekt converter script reads columns by exact name `row['Quantity']` and
  `row['Scryfall ID']` via Python's `csv.DictReader`, confirming those two literal header
  strings and comma-delimited `csv.DictReader`-compatible structure.
  Source: [ManaBox to Archidekt CSV converter (gist)](https://gist.github.com/JasonFreeberg/203c651987b124cb74e36f456a415c1d). **[Secondary, corroborating]**
- A Moxfield feature request confirms the whole-collection export "includes binder
  information which can be imported", corroborating the primary doc's "binder/list name" claim,
  though neither the TappedOut nor the MtgCsvHelper example header above shows a distinct
  binder/list-name column — plausibly because those examples came from a single-binder export.
  Source: [Improved Manabox Importing — Moxfield Feedback](https://moxfield.nolt.io/1478). **[Secondary, single source — flagged as an open discrepancy, see §5.2]**

### 1.4 Column-by-column semantics

| Column | Semantics | Confidence |
|---|---|---|
| Name | Card name. Required. | Primary |
| Set code / Set name | Scryfall's own set codes/names. Either satisfies the "set" half of the required identity; set code preferred because names drift across sites. | Primary |
| Collector number ("Card number") | The printed collector number; ManaBox aligns its set/number data to Scryfall, so this should track Scryfall's `collector_number` (a string, not purely numeric — can carry promo suffixes). | Primary (alignment to Scryfall) / inference for exact field shape |
| Foil | Card finish. Real example row uses literal value `normal` for non-foil. Search evidence (not independently verified against a literal example) suggests `foil` and `etched` as the other two values, since ManaBox tracks etched as a distinct finish. | Secondary — `normal` confirmed by literal example (§1.3); `foil`/`etched` casing **unconfirmed**, see §5.3 |
| Rarity | Example row uses literal value `mythic` (lowercase), consistent with Scryfall's own rarity vocabulary. | Secondary, single source |
| Quantity | Copies of that card/printing/condition/language/foil combination. | Primary |
| ManaBox ID | An internal ManaBox identifier (numeric in the example: `83505`). Not documented by ManaBox itself; purpose/stability across re-exports unconfirmed. | Secondary, single source |
| Scryfall ID | The card printing's Scryfall UUID. Can substitute for Name + Set entirely on import. | Primary (role) + Secondary (literal UUID format, e.g. `cb966ee6-bf1b-4bb6-9277-8de6f3918ae2`) |
| Purchase price | The price the user paid (or, if unedited at add-time, the card's market price on the day it was added to the collection) — **not** a live/current price. See §1.5. Example value `1.84` uses a `.` decimal separator. | Primary (semantics) + Secondary (literal decimal format, single source) |
| Purchase price currency | Currency the purchase price is recorded in. Example value `USD`. ManaBox's price providers span TCGplayer/Card Kingdom/Star City Games/Mana Pool (USD), Cardmarket (EUR), and Cardhoarder (MTGO's "TIX" ticket currency) — plausibly the vocabulary this column draws from, but that mapping is inference, not a stated list of legal values. | Primary (provider list) / inference for the column's exact value set |
| Misprint | Boolean-ish flag. Example value `false`. | Secondary, single source |
| Altered | Boolean-ish flag (physically altered card). Example value `false`. | Secondary, single source |
| Condition | See §1.6 — literal casing is disputed between sources. | Secondary, corroborated on the value set, disputed on exact casing |
| Language | See §1.7 — code vocabulary has documented mismatches against other tools. | Secondary, corroborated |
| Binder/list name | Present on export per ManaBox's own doc ("will include all card properties as well as the binder/list name") and per the Moxfield feature-request corroboration, but absent from both literal example headers collected here. | Primary (claim) / open discrepancy on where/when the column appears, see §5.2 |

Sources for this table beyond what's inline: [Import and export the collection](https://manabox.app/guides/collection/import-export/); [Collection F.A.Q.](https://www.manabox.app/guides/collection/faq/); [Card prices](https://www.manabox.app/guides/general/prices-in-the-app/); [StepKie/MtgCsvHelper issue #26](https://github.com/StepKie/MtgCsvHelper/issues/26).

### 1.5 "Purchase price" semantics, verbatim from ManaBox's own FAQ

Under "How does the card value change (+/- %) work?":

> "The current card value change is based on the purchase price of the card.
> If you don't edit the purchase value when adding a card to the app, the app will
> automatically use the card's price on the day you add it to your collection."
>
> "For example, if you added a card with a purchase price of $10.00, and the card's current
> value is now $15.00, your card will have a $5.00 (+50%) increase."
>
> "You can view the purchase price of any card in your collection by tapping the pencil icon
> next to the card. Additionally, in the Settings menu from the home tab, you can choose your
> preferred price provider and select which reference price to use."

Source: [Collection F.A.Q.](https://www.manabox.app/guides/collection/faq/). **[Primary]**

This matters for ingestion: "Purchase price" is a point-in-time acquisition cost (user-entered
or auto-filled at add-time), not a refreshed market value. A tutor plugin that wants current
pricing should not treat this column as live data.

### 1.6 Condition values

Two independent secondary sources agree on a 7-value, Title-Case-with-spaces vocabulary:

| ManaBox condition (Title Case) | Notes |
|---|---|
| Mint | |
| Near Mint | |
| Excellent | |
| Good | |
| Light Played | |
| Played | |
| Poor | |

Sources: [MythicHub — Importing Collection Help](https://mythichub.com/help/importing-collection?section=importing-from-manabox)
(gives this exact mapping table, ManaBox condition → MythicHub condition) and, more
importantly, a **literal parse-error quote from Moxfield's own importer failing on a real
ManaBox export**: `Could not parse card condition 'Near Mint'. on line 2`, reported in
[moxfield/moxfield-public issue #59](https://github.com/moxfield/moxfield-public/issues/59).
That second source is effectively a direct read of the literal string ManaBox wrote into a
real file. **[Secondary, corroborated by 2 sources including a literal error-message quote]**

**Conflicting claim:** [StepKie/MtgCsvHelper's CONVERSION_LIMITATIONS.md](https://github.com/StepKie/MtgCsvHelper/blob/develop/CONVERSION_LIMITATIONS.md)
describes ManaBox's condition values as snake_case tokens (`mint`, `near_mint`, `excellent`,
`good`, `light_played`, `played`, `poor`), and the literal example row quoted in §1.3 (from the
same project's issue tracker) also shows `near_mint`. This could mean the tool's docs describe
its own internal canonical naming rather than ManaBox's literal wire format, or it could mean
ManaBox's actual format really is snake_case and the other two sources normalized it for
readability when they wrote their docs/table. **This is an open, unresolved discrepancy — not
guessed at, flagged for empirical verification against a fresh real export before a parser
hard-codes either casing.** Given the Moxfield issue is a direct quote of a parse failure
against a real user file, "Near Mint" (Title Case) is the better-supported reading, but a
parser should probably normalize case/underscores defensively either way.

### 1.7 Language values

The collection guide doesn't enumerate language codes directly, but two independent sources
give partial vocabularies that disagree on the Chinese variants:

- [StepKie/MtgCsvHelper's CONVERSION_LIMITATIONS.md](https://github.com/StepKie/MtgCsvHelper/blob/develop/CONVERSION_LIMITATIONS.md)
  states ManaBox supports "the same 11 Scryfall language codes": `en, fr, de, es, it, zhs, ja,
  pt, ru, ko, zht`. **[Secondary, single source]**
- A real-world Archidekt forum thread, with a user directly comparing their ManaBox export
  against Archidekt's importer, documents these ManaBox codes instead:
  `zh_TW` (Traditional Chinese), `zh_CN` (Simplified Chinese), `es` (Spanish), `ko` (Korean),
  `ja` (Japanese, works), `de`, `pt`, `it`, `fr`. An Archidekt developer replied in-thread: "we
  maintain a key for this kind of thing. I can add the manabox codes and convert them" —
  confirming from the consuming side that ManaBox's codes are treated as their own vocabulary
  needing a translation table, not assumed identical to Archidekt's own.
  Source: [Archidekt forum — Manabox import language mismatch](https://archidekt.com/forum/thread/21948576). **[Secondary, single source, but corroborated in-thread by a maintainer's reaction]**
- A GitHub issue on the same MtgCsvHelper project ("Language on manabox to moxfield translation
  broken for japanese, russian, and chinese") shows a real pasted ManaBox CSV row using the
  literal value `ja` for Japanese, and states the tool's Japanese mapping was wrongly hard-coded
  to `jp` instead of ManaBox's actual `ja`; it also notes Russian and both Chinese variants had
  no mapping entries at all in that tool.
  Source: [StepKie/MtgCsvHelper issue #26](https://github.com/StepKie/MtgCsvHelper/issues/26). **[Secondary, single source]**

Net read: `en`, `ja`, `de`, `pt`, `it`, `fr`, `es`, `ko` look like plain lowercase ISO-ish
codes across sources. The Chinese variants are the specific point of disagreement —
`zhs`/`zht` (Scryfall's own short codes) per one source vs. `zh_CN`/`zh_TW` per a first-hand
CSV inspection. **Unconfirmed which is literally correct; verify against a fresh export before
building a language-code mapping table.**

### 1.8 Errors during import (relevant to round-tripping a previously-exported file)

Verbatim from ManaBox's own guide: "It's possible that some cards fail when importing. Most
common issue is a different naming convention with the set names. If possible, prefer to use
the Set code, as there are less chances for it to be different across sites. When errors are
encountered you will be prompted with a summary of the errors, the reason, and in which lines
they occurred. You have the option to import only the successful cards and download a CSV with
the errors detected so that you can fix them manually and import back later."
Source: [Import and export the collection](https://manabox.app/guides/collection/import-export/). **[Primary]**

Also from the same guide, on editing CSVs before reimport: "There are multiple tools to edit
CSVs. We recommend Google Sheets, which detects correctly the different columns out of the
box. Excel is another popular option, but it requires additional configuration to properly
detect the columns when the values contain commas, which is quite common in MTG." **[Primary]**
— a direct signal that card names/set names routinely contain commas (e.g. "Krenko, Mob Boss"),
so the export is properly comma-quoted CSV (RFC 4180-style), not a naive comma-split format;
any parser must use a real CSV parser, not `line.split(',')`.

---

## 2. Deck export

### 2.1 No CSV for decks — text only

ManaBox's deck import/export guide describes exactly two share options for a deck: **Export**
("creates a text file as a mean to reimport back, in other ManaBox for example") and **Share**
("has additional options for better customization" — a Link, or a customizable text file).
Neither is CSV. Source: [Import and export decks](https://www.manabox.app/guides/decks/import-export/). **[Primary]**

The deck FAQ confirms the same two-option framing: "You can share a deck as a **text** file or
as a **link**." Source: [Decks F.A.Q.](https://www.manabox.app/guides/decks/faq/). **[Primary]**

So, for the ticket's question about "deck export formats (text/CSV variants)": there is no CSV
variant for decks. CSV is a collection/binder-only export format.

### 2.2 The text format

Verbatim from the guide: "ManaBox automatically supports multiple text formats, but the most
standard format is as follows. This format is used by MTG Arena and most websites."

```
4 Tarmogoyf
3 Verdant Catacombs (MH2) 260

2 Surgical Extraction
```

(The blank line between the second and third entries appears in the site's own rendered
example; it isn't explained one way or the other — plausibly just spacing in their example, not
a format requirement. Worth confirming empirically rather than assuming it's meaningful.)

"The set and number are optional." "Chances are, if you use a different format, it will work.
If it doesn't and it includes the card name and number, feel free to contact us so we can
investigate." "Sometimes, websites use different names or set codes; in those cases, manual
updates may be necessary."
Source: [Import and export decks](https://www.manabox.app/guides/decks/import-export/). **[Primary]**

Format shape: `<quantity> <card name> (<set code>) <collector number>`, with the set code and
collector number optional. This is the same format used for collection **text** import too —
the collection guide says so explicitly: "Text import: Works the same as in decks, based on
the MTGA format."
Source: [Import and export the collection](https://manabox.app/guides/collection/import-export/). **[Primary]**

### 2.3 Custom/grouped text export

Beyond the plain re-importable export, the Share menu offers a "Custom text file" option:
"Here, you can group the cards by different properties, or even generate a list without version
information, just the card names, by using the group printings option. This is also useful for
exporting your missing cards."
Source: [Import and export decks](https://www.manabox.app/guides/decks/import-export/). **[Primary]**
This implies the plain text format's exact shape isn't fixed once "group printings" or other
grouping is applied — a parser targeting deck text exports should treat the standard
`<qty> <name> (<set>) <number>` line as the reliable, reimportable shape, and not assume
custom/grouped exports carry set/number data at all (grouping explicitly can drop version
info down to just card names).

### 2.4 URL/link import and export

For import, ManaBox accepts direct deck links from nine platforms: "Aetherhub, Archidekt,
Deckstats, Moxfield, MTGTop8, Scryfall, TappedOut, TCGplayer, and Untapped.gg", plus ManaBox's
own links, plus a generic "Import from URL" fallback.
Source: [Import and export decks](https://www.manabox.app/guides/decks/import-export/). **[Primary]**

For export/share, the Link option requires signing in to a ManaBox account; recipients using
ManaBox open it in-app, others get a browser view.
Source: [Decks F.A.Q.](https://www.manabox.app/guides/decks/faq/). **[Primary]**

This is not a data format tutor would parse directly (it's a hosted link, not a file), but it's
worth noting as the third deck-sharing surface alongside the two text options.

---

## 3. Collection CSV import — supported source apps

Not strictly an "export format" question, but relevant context: ManaBox's collection CSV
*importer* is deliberately tolerant of other apps' export formats ("ManaBox support most
popular apps and sites out of the box. So if the site you are using has a way to export a CSV,
just try to import it as is."), with one documented special case — TCGplayer's app requires
enabling the "TCGplayer ID" and "Product ID" columns under "CSV Output Settings" before its
export will work.
Source: [Import and export the collection](https://manabox.app/guides/collection/import-export/). **[Primary]**
This doesn't change tutor's parsing target (ManaBox's own export shape), but it confirms
ManaBox's own CSV column set is the "native" one to target rather than one of several tolerated
dialects.

---

## 4. Parsing-reliability gotchas, collected from real-world reports

All of these are secondary, drawn from other tools' forums/issue trackers rather than ManaBox's
own docs — ManaBox's site does not itself discuss encoding/format edge cases.

1. **Blank/alternating lines inside the CSV.** A TappedOut user reported: "it looks like
   Manabox leaves alternate lines between entries, which creates a long list of errors — which
   is fine, it seems like they can be ignored." Source: [TappedOut forum](https://tappedout.net/mtg-forum/tappedout/importing-csv-from-manabox/). **[Secondary, single source]** A parser should tolerate/skip blank rows rather than treating them as malformed data.
2. **Condition value casing is disputed** between Title-Case-with-spaces ("Near Mint") and
   snake_case ("near_mint") across the sources in §1.6. Confirmed real-world consequence: a
   Moxfield user's import failed line-by-line with `Could not parse card condition 'Near
   Mint'.` because Moxfield's importer didn't recognize ManaBox's literal condition string.
   Source: [moxfield/moxfield-public#59](https://github.com/moxfield/moxfield-public/issues/59). **[Secondary, corroborated]**
3. **Language codes don't map 1:1 onto other tools' (or possibly even Scryfall's own) language
   vocabulary**, particularly for Traditional/Simplified Chinese — see §1.7. Downstream
   consumers (Archidekt, Moxfield-adjacent tools) maintain their own manabox-specific
   translation tables rather than assuming ManaBox codes equal their own. **[Secondary,
   corroborated across 2 independent issue trackers]**
4. **Card names containing commas require real CSV quote-handling.** ManaBox's own guide
   flags this indirectly by recommending Google Sheets over Excel for editing exports, "as
   [Excel] requires additional configuration to properly detect the columns when the values
   contain commas, which is quite common in MTG." Source: [Import and export the collection](https://manabox.app/guides/collection/import-export/). **[Primary]** A parser must use a
   proper CSV/RFC-4180 parser, not naive comma-splitting.
5. **The "documented" column list and the real export column list are not the same list** —
   see §1.2 vs §1.3. A parser should be tolerant of extra/unexpected columns (Rarity, ManaBox
   ID, binder/list name) beyond the ones ManaBox's own guide names as "supported", and should
   key off header names rather than fixed column positions.
6. **Quantity can go missing from a row entirely and break naive importers.** One search
   summary of Archidekt community discussion mentioned a bug "if an import doesn't have a
   quantity column", and a Deckbox forum thread describes a large ManaBox import that showed
   card names but dropped all quantities on Deckbox's side. Neither of these was independently
   verified against a literal file — flagged as lowest confidence, included only as a signal
   to defensively validate that a Quantity column is present and populated.
   Sources: [Deckbox forum](https://deckbox.org/forum/posts/127865); general Archidekt CSV
   import forum discussion surfaced via search (not individually fetched/verified). **[Secondary,
   single/unverified — lowest confidence, included as a signal only]**

---

## 5. Open questions (unconfirmed — recommend empirical verification before building a parser)

### 5.1 Literal delimiter

ManaBox's own docs describe the format only as "CSV (Comma Separated Values)"
([source](https://manabox.app/guides/collection/import-export/)), and the one literal,
unambiguous comma-delimited example available (§1.3, from the MtgCsvHelper issue) is
comma-delimited. **Confidence: high that the delimiter is a plain comma** — but note the
TappedOut forum poster rendered their header with `|` separators, which is most likely just
their own readability formatting when pasting into a forum post, not evidence of an actual
pipe-delimited variant. No evidence of a semicolon-delimited (common EU-locale spreadsheet
default) variant was found.

### 5.2 Whether "binder/list name" is always a literal column

ManaBox's own doc says the export "will include all card properties as well as the binder/list
name" (§1.1), and a Moxfield feature request corroborates that binder info is present and
importable (§1.3). But neither literal example header collected (§1.3) shows a distinct
binder/list-name column. Possible explanations: those examples came from single-binder exports
where the app omits a redundant column, the column is present under a different header name
than expected, or the examples are simply from an older/different app version than the primary
doc reflects. **Unconfirmed — verify against a real whole-collection export spanning multiple
binders.**

### 5.3 Foil/finish literal values

Only `normal` is confirmed by a literal example (§1.3). `foil` and `etched` as the other two
values are plausible (ManaBox does track etched as a distinct finish per general search
results) but **not confirmed against a literal example row** — no foil or etched example row
was found in any source checked.

### 5.4 Character encoding and BOM

**Not documented anywhere found** — neither ManaBox's own site nor any secondary source
discusses UTF-8/BOM handling for the export file. Given the app needs to round-trip non-Latin
card names/set names (Japanese, Korean, Chinese, Russian card printings all exist and are
referenced via the Language column), the export is almost certainly UTF-8, but whether it's
emitted with or without a BOM is unknown. Recommend checking a real exported file's first bytes
before committing a parser to an encoding assumption.

### 5.5 Decimal-separator locale sensitivity

The one literal Purchase price example found (`1.84`, §1.3) uses a period. No source discusses
whether this changes for users in EU-locale phone settings (comma-decimal) or for a
non-USD/EUR purchase currency. **Unconfirmed for non-US locales** — recommend verifying with a
sample export from a device set to a comma-decimal locale before assuming period-only.

### 5.6 Rarity and Collector Number exact value shapes

Rarity's one literal example (`mythic`) is consistent with Scryfall's lowercase rarity
vocabulary (`common`/`uncommon`/`rare`/`special`/`mythic`/`bonus`), but no source enumerates
all values ManaBox actually emits. Collector Number's exact string shape (whether it preserves
non-numeric Scryfall collector numbers like promo-suffixed or `★`-suffixed numbers) is inferred
from ManaBox's general Scryfall-alignment claim, not confirmed with a literal example.

---

## Sources

Primary (manabox.app):

- [Import and export the collection](https://manabox.app/guides/collection/import-export/)
- [Import and export decks](https://www.manabox.app/guides/decks/import-export/)
- [Collection F.A.Q.](https://www.manabox.app/guides/collection/faq/)
- [Decks F.A.Q.](https://www.manabox.app/guides/decks/faq/)
- [Card prices](https://www.manabox.app/guides/general/prices-in-the-app/)
- [General F.A.Q.](https://www.manabox.app/guides/general/faq/) (checked; no export/encoding-specific content found)

Secondary:

- [Importing CSV from Manabox? — TappedOut forum](https://tappedout.net/mtg-forum/tappedout/importing-csv-from-manabox/)
- [Manabox CSV import parse errors — moxfield/moxfield-public issue #59](https://github.com/moxfield/moxfield-public/issues/59)
- [Importing Collection Help — MythicHub](https://mythichub.com/help/importing-collection?section=importing-from-manabox)
- [StepKie/MtgCsvHelper — CONVERSION_LIMITATIONS.md](https://github.com/StepKie/MtgCsvHelper/blob/develop/CONVERSION_LIMITATIONS.md)
- [StepKie/MtgCsvHelper — issue #26 (language mapping)](https://github.com/StepKie/MtgCsvHelper/issues/26)
- [Archidekt forum — Manabox import language mismatch](https://archidekt.com/forum/thread/21948576)
- [ManaBox to Archidekt CSV converter (gist)](https://gist.github.com/JasonFreeberg/203c651987b124cb74e36f456a415c1d)
- [Improved Manabox Importing — Moxfield Feedback](https://moxfield.nolt.io/1478)
- [Import .csv from manabox — Deckbox forum](https://deckbox.org/forum/posts/127865) (lowest confidence, see §4 item 6)

Checked but blocked/unusable: Mana Pool's "CSV Inventory Export - ManaBox Format" support
article (`support.manapool.com/hc/en-us/articles/26131255560855`) is behind a Cloudflare
bot-challenge and could not be retrieved by either the fetch tool or a direct request; it was
not used as a source here.
