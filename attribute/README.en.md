# Attribution workspace

English | [中文](README.md)

This directory records the inputs a local Agent used for attribution and the reports it produced. In development the default root is the repository’s `attribute/`. In production the default is `HE_DATA_DIR/attribute/`. Set `HE_ATTRIBUTION_PACKAGE_DIR` to an absolute path to override it. The paths below are relative to one `<workspace_id>/`. The API writes workspace data. Git tracks the documentation.

## Directory layout

```text
<workspace_id>/
├── attribute_skill/
│   ├── uploads/<package_id>/
│   └── snapshots/<skill_hash>/
│       ├── manifest.json
│       └── skill/{SKILL.md,make_probe_report.py,...}
├── attribute_source/
│   ├── <definition_key>/definition.md
│   └── snapshots/<source_hash>/attribute_source.md
├── attribute_input/
│   ├── sessions/<session_key>/<evidence_hash>/
│   │   ├── session_tree.json
│   │   ├── traces.json
│   │   └── trace_coverage.json
│   └── batches/<batch_id>/<case_key>/
│       ├── input_badcase.json
│       └── manifest.json
└── attribute_output/<batch_id>/<case_key>/
    ├── attempt-<random>/
    ├── logs/<attempt>/attribute_log.json
    ├── attribute_log.json
    └── probe_report.json
```

## Batches, recomputation and caching

| Trigger | batch_id | Files |
| --- | --- | --- |
| Create or change a binding to analyze current Badcases in the background | Binding generation (`binding_generation`) | One batch can span Sessions and cases, independently of an evolution Run |
| Disable caching and select a workspace Skill in the wizard | New evolution Run ID | Creates input and output for this Run and preserves earlier reports and the target binding |
| Retry a failed batch | Original batch ID | Reuses the case’s frozen inputs and creates a fresh temporary attempt when invoking Claude |
| Enable caching in the wizard | Reference to existing reports | A hit reuses the original report, inputs and batch. Cases without reports are skipped |

Session and Badcase directory names normally use the original ID. For IDs with characters such as path separators, or longer than 128 characters, the directory name is `~` followed by the SHA-256 digest of the UTF-8 ID. The input manifest retains the original IDs.

## How inputs are assembled

1. A matching call or node anywhere in the Session tree qualifies by object type and name, including unknown or different revisions. Each Badcase gets its own input. In `input_badcase.json`, `selected_target` identifies the target under evaluation. `bad_cases[0]` retains the reporting object, location and metadata.
2. Cases for the same Session share one evidence read per Runner invocation. `session_tree.json` contains normalized Agent nodes and events. `traces.json` maps Agent IDs to collected, redacted transcripts. In `trace_coverage.json`, `available_agent_ids` lists nodes with nonempty transcripts and `missing_agent_ids` lists known nodes without one. The statuses `available`, `partial` and `normalized_events_only` indicate transcripts for all known nodes, missing transcripts for some nodes or only normalized evidence, respectively. Available transcripts can contain truncated messages. A subsequent analysis can capture a new evidence version after backfill or tree changes.
3. Saving a Git Agent or Skill reads the definition at the selected commit into `attribute_source/<definition_key>/definition.md`, keyed by its raw content hash. The binding batch pins this commit and file, verifies it and redacts it for execution. It resolves the default Skill from the bundled package or a custom Skill from the workspace’s uploads. The first resolution of a Skill for a binding generation pins its package files, platform writer, execution instructions, Agent and model identity. A Run with caching disabled uses this same snapshot when the bound package is selected. Selecting another package freezes that package for the Run alone.
4. Before invoking the Agent, the platform publishes the case input directory atomically. Its manifest identifies the workspace, batch, trigger, Badcase, Session, target revision, Skill and content hashes. Once published, a retry for this case and batch reads and verifies the archived inputs. Multiple batches may reference the same Session evidence or target prompt.

## Claude working directory and report

The worker and wizard call `run_skill` with the frozen provider, model and Skill; the task text references the neutral `skills/<skill_name>/SKILL.md` layout, and the provider adapts it to its own form via `stage_skill`, optionally prepending a native prefix. Linux defaults to bubblewrap and macOS uses Seatbelt; both load the Skill from the layout the provider stages. Only an explicit `HE_ATTRIBUTION_BWRAP_ENABLED=false` on Linux selects case tools. Claude then receives the frozen `SKILL.md` as text, uses `read_evidence` to page through the inputs and `skill/` files, and calls `write_probe_report`. Each attempt has a private home. Both paths verify the writer receipt and regenerate the report from the original input before ingestion.

`attribute_log.json` records the latest finished attempt. Each `logs/<attempt>/` keeps its own history. `execution.executionMode` identifies `case-tools`, `bubblewrap` or `seatbelt`. The log includes the prompt, input manifest, Claude session ID, visible turns, tool calls and usage. The transcript read is limited to 8 MiB, with details in `transcript.status`. `report_validated` indicates a verified report. The database confirms ingestion.

## Trace a report back to its inputs

1. Take the batch and case path segments from `attribute_output/<batch_id>/<case_key>/probe_report.json`. Open `attribute_input/batches/<batch_id>/<case_key>/manifest.json` and its sibling `input_badcase.json`.
2. Read `sessionId` and `evidenceHash` from the manifest. Use the Session directory naming rule above to open `attribute_input/sessions/<session_key>/<evidenceHash>/` and inspect the tree, transcripts and coverage used at execution time.
3. `gitSource` records the repository and commit. Binding batches include the file path. Runs include the target subdirectory and read the definition at the commit resolved at launch. Use `definitionKey` to locate the target definition and `sourceHash` to locate the prompt supplied to the model. Use `skill.snapshotHash` under `attribute_skill/snapshots/` to inspect the Skill files and model identity.
4. Compare the report’s `execution_manifest.contextSnapshotHash` with the input manifest’s `inputHash` and `execution_manifest.skill.contentHash` with `skill.snapshotHash`. In SQLite, look up the originating batch by database report ID.

```sql
SELECT p.workspace_id, p.session_id, a.bad_case_id,
       COALESCE(p.binding_generation, p.created_run_id) AS batch_id,
       p.attribution_skill_name
FROM probe_reports AS p
JOIN bad_case_analysis AS a ON a.probe_id = p.probe_id
WHERE p.probe_id = :probe_id;
```

Query by the stored report ID. New platform rows use ULIDs. The file writer reproduces its 64-character SHA-256 `probe_id` from the same inputs.

`sourceHash` is the SHA-256 digest of the redacted prompt’s UTF-8 bytes. `evidenceHash` hashes the canonical JSON mapping of each of the three evidence filenames to its byte digest. `inputHash` hashes the canonical JSON mapping of the five runtime filenames to their exact text. Older reports remain readable and may predate input manifests. When backing up or pruning data, keep the workspace database records and their referenced snapshots together. Removing a referenced snapshot causes retry verification to fail.
