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
# Two things it could not do for you:
#
# * The semantic model queries Kusto **by URI**, and Fabric only generates that URI when it creates
#   *your* Eventhouse - so the model ships with placeholders.
# * A DirectQuery model over Kusto has no usable credentials until its datasource is bound. Skip
#   that and every query fails with a bare `DatasetExecuteQueriesError`.
#
# Run the cell below once. It does both, then leaves the model reading the Eventhouse under each
# user's own identity.
#
# Afterwards, run **NB_Helsinki_Realtime_Tracker** to start pulling the live HSL feed, give it a
# minute, and query `vehicle_positions` in the KQL database.

# CELL ********************

import base64
import json
import time

import requests

import notebookutils

FABRIC_API = "https://api.fabric.microsoft.com/v1"
POWERBI_API = "https://api.powerbi.com/v1.0/myorg"
WORKSPACE_ID = notebookutils.runtime.context["currentWorkspaceId"]

DATABASE_NAME = "HSL_EH"
MODEL_NAME = "Helsinki Public Transport"


def headers(audience: str = "pbi") -> dict:
    return {
        "Authorization": f"Bearer {notebookutils.credentials.getToken(audience)}",
        "Content-Type": "application/json",
    }


def lro(response):
    """Follow a Fabric long-running operation and return its result."""
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(f"{response.status_code}: {response.text[:500]}")
    if response.status_code != 202:
        return response.json() if response.content else None

    location = response.headers["Location"]
    for _ in range(60):
        time.sleep(3)
        poll = requests.get(location, headers=headers(), timeout=120).json()
        if poll.get("status") == "Succeeded":
            result = requests.get(location.rstrip("/") + "/result", headers=headers(), timeout=120)
            return result.json() if result.content else None
        if poll.get("status") == "Failed":
            raise RuntimeError(f"operation failed: {poll}")
    raise TimeoutError("operation did not finish")


def find(kind: str, name: str) -> dict:
    response = requests.get(f"{FABRIC_API}/workspaces/{WORKSPACE_ID}/{kind}",
                            headers=headers(), timeout=120)
    response.raise_for_status()
    for item in response.json()["value"]:
        if item["displayName"] == name:
            return item
    raise LookupError(f"no {kind} called {name!r} in this workspace")


# ---------------------------------------------------------------- 1. point the model at Kusto
database = find("kqlDatabases", DATABASE_NAME)
cluster = database["properties"]["queryServiceUri"]
model = find("semanticModels", MODEL_NAME)
print(f"KQL database : {database['id']}")
print(f"query URI    : {cluster}")

definition = lro(requests.post(
    f"{FABRIC_API}/workspaces/{WORKSPACE_ID}/semanticModels/{model['id']}/getDefinition",
    headers=headers(), timeout=180))

parts = definition["definition"]["parts"]
patched = 0
for part in parts:
    raw = base64.b64decode(part["payload"]).decode("utf-8")
    new = raw.replace("__KUSTO_QUERY_URI__", cluster).replace("__KUSTO_DATABASE__", database["id"])
    if new != raw:
        part["payload"] = base64.b64encode(new.encode("utf-8")).decode("ascii")
        patched += 1

if patched:
    lro(requests.post(
        f"{FABRIC_API}/workspaces/{WORKSPACE_ID}/semanticModels/{model['id']}/updateDefinition",
        headers=headers(), json={"definition": {"parts": parts}}, timeout=300))
    print(f"bound the model to this workspace ({patched} file(s) rewritten)")
else:
    print("model already bound - nothing to rewrite")

# ------------------------------------------------------------- 2. bind the datasource credentials
# Without this every DAX query fails with a bare DatasetExecuteQueriesError. Ownership has to be
# taken first, or the datasource endpoints are not reachable.
takeover = requests.post(
    f"{POWERBI_API}/groups/{WORKSPACE_ID}/datasets/{model['id']}/Default.TakeOver",
    headers=headers(), timeout=120)
print(f"takeover: HTTP {takeover.status_code}")

datasource = None
for _attempt in range(12):
    listing = requests.get(
        f"{POWERBI_API}/groups/{WORKSPACE_ID}/datasets/{model['id']}/datasources",
        headers=headers(), timeout=120)
    values = listing.json().get("value") if listing.ok else None
    if values:
        datasource = values[0]
        break
    time.sleep(10)

if not datasource:
    raise RuntimeError("the model reported no datasource - re-run this cell in a minute")

gateway_id = datasource["gatewayId"]
datasource_id = datasource["datasourceId"]
print(f"datasource: gateway={gateway_id} id={datasource_id}")

# A token for the cluster itself: the audience https://kusto.fabric.microsoft.com is not
# registered in every tenant, and an empty credentialData array is rejected outright.
kusto_token = notebookutils.credentials.getToken(cluster)
credentials = json.dumps({"credentialData": [{"name": "accessToken", "value": kusto_token}]})
url = f"{POWERBI_API}/gateways/{gateway_id}/datasources/{datasource_id}"

for label, end_user_sso in (("seed with a Kusto token", False), ("switch to end-user SSO", True)):
    patch = requests.patch(url, headers=headers(), timeout=120, json={"credentialDetails": {
        "credentialType": "OAuth2",
        "credentials": credentials,
        "encryptedConnection": "Encrypted",
        "encryptionAlgorithm": "None",
        "privacyLevel": "Organizational",
        "useEndUserOAuth2Credentials": end_user_sso,
    }})
    print(f"{label}: HTTP {patch.status_code}")
    if patch.status_code not in (200, 204):
        raise RuntimeError(f"{label} failed: {patch.text[:400]}")

print("\nReady. Run NB_Helsinki_Realtime_Tracker next to start ingestion.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
