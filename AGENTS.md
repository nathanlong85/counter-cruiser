<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

## Command Registry

Before running or suggesting any shell command — and before retrying after a failure —
check command registries (use whichever exist):

1. Project: .agents/rules/local/command-registry/ (if present)
2. Global: ~/.agents/rules/command-registry/ (or $CREG_GLOBAL_PATH if set)
Project wins on conflicts. For each registry found:
  a. Identify the right topic file from index.md routing table.
  b. Search (grep/rg) for the `## snake_case_id` or keyword. Read only that section.
     For precise tag filtering: `creg search --tags tag1[,tag2]` (or `--any-tags`, `--exclude-tags`).
  c. Prefer: exact verified → adapt template → closest intent.
  d. If retrying after a failure, re-scan `anti_patterns` in the matched entry before changing command shape.

After a command succeeds that is not in the registry: use `creg add` to record it that turn.
  - Contains project-specific path/host/script → project registry (no -g)
  - Generic, works across repos → global registry (creg add ... -g)
  Print one line to the user: `Command registry: added <id>` or `Command registry: updated <id>`.

Extend existing entries. Avoid near-duplicates across topic files.
Registry wins for command shape. Project rules win for policy.
