# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. The `gh` CLI is **not** available in this repo's agent environments — do not use it. Use the GitHub MCP server tools (`mcp__github__*`) when the session has them, and fall back to the GitHub REST API (`curl` against `https://api.github.com`) otherwise. Ticket dependency mapping has no MCP or CLI equivalent and always goes via the REST API.

Infer `<owner>/<repo>` from `git remote -v`.

## REST conventions

Every REST call carries these headers (token from `$GH_TOKEN` or `$GITHUB_TOKEN`):

```sh
curl -sS https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28"
```

The operations below give METHOD and path only; add the headers (plus `-X <METHOD>` and `-d '<json>'`) as shown above. Use a heredoc for multi-line JSON bodies.

## Operations

- **Create an issue**: MCP `issue_write` (method `create`), or `POST /repos/<o>/<r>/issues` with `{"title": "...", "body": "...", "labels": [...]}`.
- **Read an issue (with comments and labels)**: MCP `issue_read`, or `GET /repos/<o>/<r>/issues/<n>` plus `GET /repos/<o>/<r>/issues/<n>/comments`.
- **List issues**: MCP `list_issues` / `search_issues`, or `GET /repos/<o>/<r>/issues?state=open&labels=...` — note this endpoint also returns PRs; drop entries carrying a `pull_request` key.
- **Comment on an issue**: MCP `add_issue_comment`, or `POST /repos/<o>/<r>/issues/<n>/comments` with `{"body": "..."}`.
- **Apply / remove labels**: MCP `issue_write` (method `update`), or `POST /repos/<o>/<r>/issues/<n>/labels` with `{"labels": ["..."]}` / `DELETE /repos/<o>/<r>/issues/<n>/labels/<name>`.
- **Close**: comment first, then MCP `issue_write` (method `update`, state `closed`), or `PATCH /repos/<o>/<r>/issues/<n>` with `{"state": "closed", "state_reason": "completed"}` (`"not_planned"` for wontfix/duplicates).

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues:

- **Read a PR**: MCP `pull_request_read`, or `GET /repos/<o>/<r>/pulls/<n>`; for the diff, repeat with `Accept: application/vnd.github.diff`.
- **List external PRs for triage**: MCP `list_pull_requests`, or `GET /repos/<o>/<r>/pulls?state=open`, then keep only `author_association` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: PRs are issues to those endpoints — use the issue operations above with the PR's number.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — `GET /repos/<o>/<r>/issues/42` and check for the `pull_request` key.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Read the issue with its comments as above.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue: MCP `sub_issue_write` (method `add`), or `POST /repos/<o>/<r>/issues/<map>/sub_issues` with `{"sub_issue_id": <child-db-id>}` — the child's numeric **database id** (`GET /repos/<o>/<r>/issues/<n>` → `.id`), not the `#number`. Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. REST API only — no MCP tool covers dependencies. Add an edge with `POST /repos/<o>/<r>/issues/<child>/dependencies/blocked_by` and body `{"issue_id": <blocker-db-id>}`, where `<blocker-db-id>` is the blocker's numeric **database id** (`GET /repos/<o>/<r>/issues/<n>` → `.id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` on each issue (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (open issues scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: assign yourself — resolve your login via MCP `get_me` or `GET /user`, then `POST /repos/<o>/<r>/issues/<n>/assignees` with `{"assignees": ["<login>"]}` — the session's first write.
- **Resolve**: comment the answer, close the issue, then append a context pointer (gist + link) to the map's Decisions-so-far.
