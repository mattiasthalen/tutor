# Scryfall card data for deck checks

Research for issue [#4](https://github.com/mattiasthalen/tutor/issues/4) (child of the wayfinder map, issue #2): what card data the **tutor** plugin can rely on for deck checks, and how it should be fetched. Primary source is Scryfall's own API documentation at <https://scryfall.com/docs/api> and its sub-pages; every claim below is cited to the specific page (and, where the page has one, the specific anchor). A handful of claims are corroborated with a live, gently-rate-limited spot check against `api.scryfall.com` on 2026-08-18, noted explicitly where used.

## Bottom line

- Use the **bulk data files**, not the live REST API, as the source of truth for the collection-wide data a deck check needs (mana value, color identity, type line, legalities, oracle text). They are refreshed once every 12–24 hours and are meant for exactly this kind of bulk, repeated lookup ([Bulk Data Files](https://scryfall.com/docs/api/bulk-data), [Rate Limits](https://scryfall.com/docs/api/rate-limits)).
- ManaBox's "Scryfall ID" column is Scryfall's card-level `id` (a UUID, distinct from `oracle_id`). It resolves directly via `GET /cards/:id` for one card, or via `POST /cards/collection` for up to 75 cards per request when doing live lookups ([Card Objects — Core Card Fields](https://scryfall.com/docs/api/cards#core-card-fields), [GET /cards/:id](https://scryfall.com/docs/api/cards/id), [POST /cards/collection](https://scryfall.com/docs/api/cards/collection)).
- All the fields a deck check needs — `cmc`, `color_identity`, `type_line`, `legalities` (including `commander`), `prices`, `oracle_text` — are plain properties on the Card object, documented on one page ([Card Objects](https://scryfall.com/docs/api/cards)).
- Every request to `api.scryfall.com` must carry a `User-Agent` and an `Accept` header, and per-endpoint hard rate limits apply (2/second for the identifier-based endpoints, 10/second for everything else) ([API Documentation — Required Headers](https://scryfall.com/docs/api#required-headers), [Rate Limits](https://scryfall.com/docs/api/rate-limits)).
- Offline operation is realistic: download one bulk file (Oracle Cards is smallest and sufficient for gameplay-only checks), decompress the gzipped JSONL, and query it locally — no live API calls needed for a deck check at all, except to backfill anything newly added to the collection that isn't in the last bulk snapshot yet.

## REST endpoints vs. bulk data files

Scryfall exposes both a normal REST API (`https://api.scryfall.com`) and daily bulk exports, and its own docs are explicit about when to use which:

> "We encourage you to cache the data you download from Scryfall or process it locally in your own system, at least for 24 hours. Scryfall provides our entire database compressed for download in daily bulk data files. If you need to rapidly look up card names, prices, or resolve a large number of card images, you must use the bulk data files."
> — [Rate Limits](https://scryfall.com/docs/api/rate-limits)

The API itself is a "REST-like API for ingesting our card data programmatically," served only over HTTPS (TLS 1.2+) at `https://api.scryfall.com`, with UTF-8 responses ([API Documentation — Endpoint Details](https://scryfall.com/docs/api#endpoint-details)).

For a deck check that needs to validate an entire ManaBox export (hundreds to thousands of cards) against legality, color identity, and mana value, the bulk files are the right tool: one download instead of hundreds/thousands of rate-limited requests, and Scryfall's own guidance points there for exactly this "large number of" lookups case. The REST endpoints remain useful for: single fresh lookups (e.g., a card just added to the collection since the last bulk sync), and the batch `/cards/collection` endpoint for small-to-medium live lookups (see below).

## Bulk data files

Scryfall publishes daily exports as `bulk_data` objects, retrievable via `GET https://api.scryfall.com/bulk-data` (list) or `GET /bulk-data/:id` / `GET /bulk-data/:type` (single file's metadata) ([Bulk Data Files](https://scryfall.com/docs/api/bulk-data)). Key facts from that page:

- Each file is a **gzip-compressed JSON Lines archive** (`.jsonl.gz`, not `.tar.gz`); many languages can stream it line-by-line straight out of the gzip stream without loading the whole file into memory. The download URL is the `jsonl_download_uri` property and its filename embeds the generation timestamp, so URLs change daily ([Bulk Data Files](https://scryfall.com/docs/api/bulk-data)).
- "Bulk data is only collected once every 12-24 hours. You can use the card API methods to retrieve fresh objects instead. You can also use the `/cards/manifest` method to check for anything that has changed on Scryfall." ([Bulk Data Files](https://scryfall.com/docs/api/bulk-data)).
- Price data included in bulk files "should be considered dangerously stale after 24 hours" and is for trend/estimate purposes only, not a storefront ([Bulk Data Files](https://scryfall.com/docs/api/bulk-data)).
- Gameplay data (names, oracle text, mana costs, etc.) changes far less often than prices — the same page repeats the guidance that weekly or post-set-release downloads are "most likely sufficient" if that's all you need.

Files available today (sizes and `type` slugs confirmed live via `GET https://api.scryfall.com/bulk-data` on 2026-08-18; descriptions and the "Last Updated" cadence from the docs page):

| File (docs name) | `type` | Compressed size | Last updated (as observed) | What it contains |
|---|---|---|---|---|
| Oracle Cards | `oracle_cards` | 23.4 MB | 2026-08-18 09:01 UTC | One card object per unique Oracle ID — the most up-to-date recognizable printing of each card |
| Unique Artwork | `unique_artwork` | 35.7 MB | 2026-08-18 09:02 UTC | One card object per unique artwork |
| Default Cards | `default_cards` | 73.9 MB | 2026-08-18 09:05 UTC | Every card object, English (or the sole printed language if English doesn't exist) |
| All Cards | `all_cards` | 374 MB | 2026-08-18 09:17 UTC | Every card object, every language |
| Rulings | `rulings` | 5.09 MB | 2026-08-18 09:00 UTC | All rulings, keyed to cards by `oracle_id` |
| Art Tags | `art_tags` | 12 MB | 2026-08-18 09:01 UTC | Community-sourced illustration tags (Tagger project) |
| Oracle Tags | `oracle_tags` | 5.58 MB | 2026-08-18 09:00 UTC | Community-sourced Oracle (gameplay) tags (Tagger project) |

Source: [Bulk Data Files](https://scryfall.com/docs/api/bulk-data#files) (sizes/descriptions/cadence) and a live `GET /bulk-data` request (exact `type` slugs and byte-for-byte sizes: 24,529,175 / 37,419,909 / 77,517,951 / 391,690,099 / 5,341,262 / 12,536,373 / 5,849,575 bytes respectively).

For tutor's purposes, **Oracle Cards** is almost certainly the right file: it's the smallest, and because a deck check cares about legality/color identity/mana value/oracle text rather than which specific printing is in a binder, one row per Oracle ID is exactly the right granularity. Fall back to **Default Cards** only if a check needs print-specific data (e.g., a specific `set`/`collector_number`/finish that ManaBox recorded, or per-printing `prices`).

## Looking up cards by Scryfall ID

ManaBox export rows carry a Scryfall ID; that value is Scryfall's card-level `id` field — "A unique ID for this card in Scryfall's database," a UUID — which is distinct from `oracle_id`, "a unique ID for this card's oracle identity" that stays constant across reprints ([Card Objects — Core Card Fields](https://scryfall.com/docs/api/cards#core-card-fields)). `id` is print-specific (one UUID per printing/edition); `oracle_id` is card-identity-specific (shared across reprints). Since ManaBox tracks physical cards a person owns, its "Scryfall ID" is the print-level `id`, matching what `GET /cards/:id` and the `id` identifier schema of `/cards/collection` expect.

**Single-card lookup — `GET /cards/:id`**: "Returns a single card with the given Scryfall ID." Supports `json`, `text`, or `image` response formats via the `format` parameter (default `json`) ([GET /cards/:id](https://scryfall.com/docs/api/cards/id)). Example from the docs: `GET https://api.scryfall.com/cards/56ebc372-aabd-4174-a943-c7bf59e5028d`.

**Batch lookup — `POST /cards/collection`**: "Accepts a JSON array of card identifiers, and returns a List object with the collection of requested cards. A maximum of **75 card references** may be submitted per request. The request must be posted with Content-Type as `application/json`." Rate limit: 2 requests/second (500 ms) ([POST /cards/collection](https://scryfall.com/docs/api/cards/collection)). Each identifier object can use one of several schemas — `id` (Scryfall UUID), `mtgo_id`, `multiverse_id`, `oracle_id`, `illustration_id`, `name`, `name`+`set`, or `collector_number`+`set` — and different schemas can be mixed within one request. Cards not found come back in a separate `not_found` array rather than breaking positional order, so the docs explicitly warn: "you should not rely on positional index alone while parsing the data" ([POST /cards/collection](https://scryfall.com/docs/api/cards/collection)).

I verified this endpoint live: `POST https://api.scryfall.com/cards/collection` with a two-item body mixing an `id` identifier and a `name` identifier returned `{"object":"list","not_found":[],"data":[...]}` with both cards resolved correctly, matching the documented shape (2026-08-18 spot check).

For a full ManaBox collection (typically far more than 75 cards), `/cards/collection` would need to be chunked into batches of 75 and paced at 2/second — workable for a one-off reconciliation, but the bulk file is still the better default for whole-collection deck checks per Scryfall's own guidance above.

**ID stability**: Scryfall IDs are normally permanent, but the docs describe a `/migrations` mechanism for the rare cases where a card entry is found to be wrong or removed: a migration has a `migration_strategy` of either `merge` ("update your records to replace the given old Scryfall ID with the new ID") or `delete` ("the given UUID is being discarded, and no replacement data is being provided") ([Card Migrations](https://scryfall.com/docs/api/migrations)). Practical implication for tutor: a `GET /cards/:id` (or a bulk-file lookup) that comes back empty for an ID recorded by ManaBox should not be treated as a hard failure — fall back to a `name`+`set`+`collector_number` identifier (also supported by `/cards/collection`) and, if reconciling systematically, consult `GET /migrations` ([Card Migrations](https://scryfall.com/docs/api/migrations)).

## Fields available per card

The Card object is documented in three groups on one page ([Card Objects](https://scryfall.com/docs/api/cards)); the fields most relevant to deck checks:

| Field | Section | Type | Notes |
|---|---|---|---|
| `id` | [Core Card Fields](https://scryfall.com/docs/api/cards#core-card-fields) | UUID | Scryfall ID for this specific print — what ManaBox exports |
| `oracle_id` | [Core Card Fields](https://scryfall.com/docs/api/cards#core-card-fields) | UUID, nullable | Stable across reprints of the same card (absent only for the `reversible_card` layout, where it lives on each face instead) |
| `name` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | String | Multi-face cards join both names with `␣//␣` |
| `mana_cost` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | String, nullable | `""` if absent — the docs note this is *not* the same as a cost of `{0}` |
| `cmc` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | Decimal | "The card's mana value. Note that some funny cards have fractional mana costs." |
| `color_identity` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | Colors (array) | "This card's color identity" — the field Commander deckbuilding rules key off of |
| `colors` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | Colors, nullable | Card's own colors; on multi-faced cards may live on `card_faces` instead |
| `type_line` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | String | e.g. `"Legendary Creature — Human Wizard"` |
| `oracle_text` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | String, nullable | Current rules text |
| `keywords` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | Array | e.g. `["Flying", "Cumulative upkeep"]` |
| `legalities` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | Object | "An object describing the legality of this card across play formats. Possible legalities are `legal`, `not_legal`, `restricted`, and `banned`." |
| `game_changer` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | Boolean, nullable | "True if this card is on the Commander Game Changer list" |
| `card_faces` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | Array, nullable | Present for multi-face cards (split/flip/transform/MDFC); per-face `mana_cost`, `type_line`, `oracle_text`, etc. live here instead of on the parent object |
| `prices` | [Print Fields](https://scryfall.com/docs/api/cards#print-fields) | Object | "An object containing daily price information for this card, including `usd`, `usd_foil`, `usd_etched`, `eur`, `eur_foil`, `eur_etched`, and `tix` prices, as strings" |
| `set` / `collector_number` | [Print Fields](https://scryfall.com/docs/api/cards#print-fields) | String | Set code and collector number for this specific printing — usable as a fallback identifier |
| `rarity` | [Print Fields](https://scryfall.com/docs/api/cards#print-fields) | String | One of `common`, `uncommon`, `rare`, `special`, `mythic`, `bonus` |
| `reserved` | [Gameplay Fields](https://scryfall.com/docs/api/cards#gameplay-fields) | Boolean | "True if this card is on the Reserved List" |

**Legalities format keys**: the docs prose only defines the four legality *values* (`legal`/`not_legal`/`restricted`/`banned`); it doesn't enumerate the format keys inline. Live-checking a card (`GET /cards/named?exact=Sol%20Ring`, 2026-08-18) shows the `legalities` object keyed by format, including `commander` (Sol Ring: `"commander": "legal"`), alongside `standard`, `future`, `historic`, `timeless`, `gladiator`, `pioneer`, `modern`, `legacy`, `pauper`, `vintage`, `penny`, `oathbreaker`, `standardbrawl`, `brawl`, `competitivebrawl`, `alchemy`, `paupercommander`, `duel`, `oldschool`, `premodern`, `predh`, and `tlr`. So `card.legalities.commander` is exactly the field tutor would check for Commander-format legality per card.

**Color arrays**: wherever the API returns a set of colors (`colors`, `color_identity`, `produced_mana`), it's an array of single uppercase letters — `W`, `U`, `B`, `R`, `G` — with `C` for colorless mana in `produced_mana`; a null/missing color field means "not pertinent," not "colorless," and array order is not guaranteed ([Colors and Costs](https://scryfall.com/docs/api/colors)).

## Rate limits and required headers

Per-endpoint hard limits from the dedicated rate-limits page ([Rate Limits](https://scryfall.com/docs/api/rate-limits)):

| Endpoint | Limit |
|---|---|
| `/cards/search` | 2/second (500 ms) |
| `/cards/named` | 2/second (500 ms) |
| `/cards/random` | 2/second (500 ms) |
| `/cards/collection` | 2/second (500 ms) |
| `/cards/manifest` | 10/minute (6,000 ms) |
| All other methods | 10/second (100 ms) |

(Note: the `/cards/manifest` page itself separately states its own limit as "10/minute (10,000ms)" — [GET /cards/manifest](https://scryfall.com/docs/api/cards/manifest) — a minor inconsistency with the rate-limits page's 6,000 ms figure for the same "10/minute" limit; either way, staying at or below 10 requests/minute to that endpoint is safe under both statements.)

Direct file downloads from `*.scryfall.io` (i.e., the bulk data files and images) are **not** rate-limited ([Rate Limits](https://scryfall.com/docs/api/rate-limits)).

Exceeding a limit can return `HTTP 429 Too Many Requests`, which locks the caller out for 30 seconds; continued overloading risks a temporary or permanent application ban, and the docs state plainly: "It is not acceptable to ignore HTTP 429 responses. You must act to reduce your application's overages." ([Rate Limits](https://scryfall.com/docs/api/rate-limits)).

**Required headers**: "All HTTP requests to `api.scryfall.com` must include a `User-Agent` header and an `Accept` header." The `User-Agent` "must be accurate to your usage context" — e.g. `MTGExampleApp/1.0` for a script/app, not whatever an HTTP library defaults to; browser JS callers should instead leave the browser's own `User-Agent` intact. `Accept` just needs to be present with a reasonable value, e.g. `Accept: */*` or `Accept: application/json;q=0.9,*/*;q=0.8` ([API Documentation — Required Headers](https://scryfall.com/docs/api#required-headers)). For tutor, something like `User-Agent: tutor/<version> (+https://github.com/mattiasthalen/tutor)` with `Accept: application/json` satisfies this.

## Caching guidance

Scryfall's stated guidance, all from the [Rate Limits](https://scryfall.com/docs/api/rate-limits) and [Bulk Data Files](https://scryfall.com/docs/api/bulk-data) pages:

- Cache/process downloaded data locally "at least for 24 hours" rather than re-fetching.
- Prices update once per day; requesting more often than every 24 hours will not surface new prices, and bulk-file prices should be treated as "dangerously stale after 24 hours" for anything beyond trend/estimate use.
- Gameplay data (names, oracle text, mana costs, legalities, etc.) changes far less often than prices; downloading weekly, or right after a new set releases, is called out as "most likely sufficient" if gameplay data is all a consumer needs.
- Bulk data itself is only regenerated once every 12–24 hours, so refreshing tutor's local snapshot more than roughly once a day gains nothing — for anything fresher, use the live per-card/collection endpoints, or `GET /cards/manifest` to cheaply detect what changed since the last sync (it returns lightweight per-card comparison data, 15,000 entries per page, and the docs say to "hydrate any Card objects you are further interested in using other methods" — it's a change-detection index, not a full data source) ([GET /cards/manifest](https://scryfall.com/docs/api/cards/manifest)).

Applied to tutor: a deck check run against a cached bulk snapshot that's under ~24 hours old is fully within Scryfall's own guidance and needs no live calls at all; a snapshot older than that is still fine for legality/oracle-text checks (weekly is explicitly endorsed) but should be treated as stale for price-sensitive checks.

## Offline options

The bulk data files are effectively tutor's offline mode: download `oracle_cards` (or `default_cards`/`all_cards` if print-level fidelity is needed) as a `.jsonl.gz`, decompress once, and load it into whatever local structure the deck-check logic wants (e.g., keyed by `id` and/or `oracle_id`) ([Bulk Data Files](https://scryfall.com/docs/api/bulk-data)). Because the format is JSON Lines, it can be streamed and filtered without holding the whole decompressed file in memory, and because the direct `data.scryfall.io` file host is unrated-limited, refreshing the local snapshot is cheap even on a daily cron ([Bulk Data Files](https://scryfall.com/docs/api/bulk-data), [Rate Limits](https://scryfall.com/docs/api/rate-limits)). Once loaded locally, every field a deck check needs — `cmc`, `color_identity`, `type_line`, `legalities.commander`, `oracle_text`, `prices` — is answerable with zero network calls; the only reason to reach the live API is a card newly added to the ManaBox export since the last bulk refresh (handle with a one-off `GET /cards/:id`, or a `/cards/collection` batch call for several such cards at once).

## Sources

- [API Documentation](https://scryfall.com/docs/api) (base URL, TLS requirement, required headers, data-use terms)
- [Rate Limits](https://scryfall.com/docs/api/rate-limits)
- [Bulk Data Files](https://scryfall.com/docs/api/bulk-data)
- [Card Objects](https://scryfall.com/docs/api/cards) (all field definitions)
- [GET /cards/:id](https://scryfall.com/docs/api/cards/id)
- [POST /cards/collection](https://scryfall.com/docs/api/cards/collection)
- [GET /cards/named](https://scryfall.com/docs/api/cards/named)
- [GET /cards/search](https://scryfall.com/docs/api/cards/search)
- [GET /cards/manifest](https://scryfall.com/docs/api/cards/manifest)
- [Card Migrations](https://scryfall.com/docs/api/migrations)
- [Colors and Costs](https://scryfall.com/docs/api/colors)
- [List Objects](https://scryfall.com/docs/api/lists)
- [Error Objects](https://scryfall.com/docs/api/errors)
- Live spot checks against `api.scryfall.com` (2026-08-18): `GET /bulk-data`, `GET /cards/named?exact=Sol%20Ring`, `POST /cards/collection`
