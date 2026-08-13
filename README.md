# Helsinki Public Transport - Fabric workspace export

Source repository for the **Helsinki Public Transport** entry in
[Fabric Jumpstart](https://jumpstart.fabric.microsoft.com). Everything under `workspace/` is an
item definition that `fabric-jumpstart` deploys into your workspace with
[fabric-cicd](https://microsoft.github.io/fabric-cicd/).

> **Author: Kevin Thomas.** The original Helsinki real-time transit solution and its Real-Time
> Intelligence architecture are his. Packaged as a jumpstart by Alexander Korn.

Vehicle data comes from the public
[HSL GTFS-RT feeds](https://hsldevcom.github.io/gtfs_rt/) (Helsingin seudun liikenne). No API key
is required.

## Install

Run in a Fabric notebook:

```python
%pip install -q fabric-jumpstart
import fabric_jumpstart as jumpstart
jumpstart.install("helsinki-public-transport")
```

Then open **`00_start_here`** and run it. That step is not optional - see below.

## What lands in the workspace

| Item | Type | Role |
|---|---|---|
| `NB_Helsinki_Realtime_Tracker` | Notebook | Polls the HSL GTFS-RT feeds, decodes the protobuf and posts batches to the Eventstream. Scheduled hourly, 58-minute budget per run. |
| `ES_Helsinki_Transport_Events` | Eventstream | Custom-endpoint ingress into the Eventhouse. |
| `Helsinki_Public_Transport_EH` | Eventhouse | Hosts the KQL database. |
| `HSL_EH` | KQLDatabase | `raw_events` plus update policies that fan it out into `vehicle_positions`, `trip_updates` and `alerts`, and a materialized view `last_vehicle_position`. |
| `Helsinki Public Transport` | SemanticModel | DirectQuery over Kusto. |
| `00_start_here` | Notebook | Binds the semantic model to *this* workspace. |

## Why `00_start_here` exists

Two values in the semantic model cannot be known when this repo is written:

* the **Kusto query URI**, which Fabric generates per Eventhouse, and
* the **KQL database id**.

They also cannot be resolved during the install: fabric-cicd publishes `SemanticModel` at position
11 of its serial order and `KQLDatabase` at 15, so a model that referenced the database would fail
before the database existed. The model therefore ships with `__KUSTO_QUERY_URI__` and
`__KUSTO_DATABASE__` placeholders, and `00_start_here` rewrites them afterwards.

It also binds the datasource credentials - takes ownership, seeds a Kusto token, then switches to
end-user SSO. Without that every DAX query fails with a bare `DatasetExecuteQueriesError`.

## Repo layout notes

If you regenerate this export, two things matter:

* `.platform` must carry a **real** `logicalId`. fabric-cicd skips the all-zero default, so
  cross-item references are never rewritten and the deployment silently points at the source
  workspace. A `getDefinition` export produces exactly that all-zero id.
* The Eventstream destination's `workspaceId` must be the all-zero placeholder. fabric-cicd
  substitutes the target workspace only when the value *is* all-zero; a real id is rejected as a
  cross-workspace destination, and omitting the field is rejected as invalid.

## Licence and attribution

Code in this repository is MIT (see `LICENSE`).

Vehicle data: *Helsingin seudun liikenne (HSL)*, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). This repository redistributes none of
it - the notebook fetches it live.
