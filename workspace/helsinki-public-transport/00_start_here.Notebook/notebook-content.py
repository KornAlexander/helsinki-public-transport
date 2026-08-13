# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Helsinki Public Transport - start here
#
# The jumpstart has deployed the Eventhouse, its KQL database, the Eventstream, the producer
# notebook and the semantic model.
#
# One thing it could not do for you: the semantic model queries Kusto by URI, and Fabric only
# generates that URI when it creates *your* Eventhouse. The model therefore ships with placeholders.
# Run the cell below once and it will point the model at the database in this workspace.
#
# After that:
#
# 1. Run **NB_Helsinki_Realtime_Tracker** to start pulling the live HSL feed into the Eventstream.
# 2. Give it a minute, then query `vehicle_positions` in the KQL database.
# 3. Optionally install the matching map app from the Awesome Rayfin gallery and point its
#    connector at the semantic model.

# CELL ********************

import re
import time

import requests

import notebookutils

API = "https://api.fabric.microsoft.com/v1"
WORKSPACE_ID = notebookutils.runtime.context["currentWorkspaceId"]
HEADERS = {
    "Authorization": f"Bearer {notebookutils.credentials.getToken('pbi')}",
    "Content-Type": "application/json",
}

DATABASE_NAME = "HSL_EH"
MODEL_NAME = "Helsinki Public Transport"


def lro(response):
    """Follow a Fabric long-running operation and return its result."""
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(f"{response.status_code}: {response.text[:500]}")
    if response.status_code != 202:
        return response.json() if response.content else None

    location = response.headers.get("Location")
    for _ in range(60):
        time.sleep(3)
        poll = requests.get(location, headers=HEADERS, timeout=120).json()
        if poll.get("status") == "Succeeded":
            result = requests.get(location.rstrip("/") + "/result", headers=HEADERS, timeout=120)
            return result.json() if result.content else None
        if poll.get("status") == "Failed":
            raise RuntimeError(f"operation failed: {poll}")
    raise TimeoutError("operation did not finish")


def find(kind: str, name: str) -> dict:
    items = requests.get(f"{API}/workspaces/{WORKSPACE_ID}/{kind}", headers=HEADERS, timeout=120)
    items.raise_for_status()
    for item in items.json()["value"]:
        if item["displayName"] == name:
            return item
    raise LookupError(f"no {kind} called {name!r} in this workspace")


database = find("kqlDatabases", DATABASE_NAME)
query_uri = database["properties"]["queryServiceUri"]
print(f"KQL database : {database['id']}")
print(f"query URI    : {query_uri}")

model = find("semanticModels", MODEL_NAME)
definition = lro(
    requests.post(
        f"{API}/workspaces/{WORKSPACE_ID}/semanticModels/{model['id']}/getDefinition",
        headers=HEADERS,
        timeout=180,
    )
)

import base64

parts = definition["definition"]["parts"]
patched = 0
for part in parts:
    raw = base64.b64decode(part["payload"]).decode("utf-8")
    new = raw.replace("__KUSTO_QUERY_URI__", query_uri).replace("__KUSTO_DATABASE__", database["id"])
    if new != raw:
        part["payload"] = base64.b64encode(new.encode("utf-8")).decode("ascii")
        patched += 1
        print(f"patched {part['path']}")

if patched == 0:
    print("\nNothing to patch - the model is already bound to this workspace.")
else:
    lro(
        requests.post(
            f"{API}/workspaces/{WORKSPACE_ID}/semanticModels/{model['id']}/updateDefinition",
            headers=HEADERS,
            json={"definition": {"parts": parts}},
            timeout=300,
        )
    )
    print(f"\nBound '{MODEL_NAME}' to {DATABASE_NAME} in this workspace ({patched} file(s)).")

print(
    "\nNext: run NB_Helsinki_Realtime_Tracker to start ingestion, then refresh the semantic model."
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
