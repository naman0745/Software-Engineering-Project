# TrustGrid API Reference

Base URL: `http://localhost:5000`

All request bodies are JSON unless noted. All responses are JSON.

---

## Authentication

### `POST /register`
Register a new node. One node per device (IP address) is enforced.

**Request**
```json
{
  "node_id": "alpha",
  "key":     "mysecretkey",
  "company": "Bank Alpha"
}
```

**Response `200`**
```json
{ "success": true, "message": "Registration complete. You can now log in." }
```

**Errors**
| Code | Reason |
|------|--------|
| 400 | Missing fields |
| 403 | IP already has a registered node |
| 409 | node_id already exists |

---

### `POST /login`
Authenticate an existing node.

**Request**
```json
{ "node_id": "alpha", "key": "mysecretkey" }
```

**Response `200`**
```json
{
  "success": true,
  "node_id": "alpha",
  "company": "Bank Alpha",
  "message": "Welcome back, Bank Alpha!"
}
```

**Errors**
| Code | Reason |
|------|--------|
| 400 | Missing fields |
| 401 | Incorrect key |
| 404 | Node not found |

---

### `POST /reset_key`
Reset a node's key. Requires company name as proof of identity.
The original key is unrecoverable (stored as SHA-256 hash only).

**Request**
```json
{
  "node_id": "alpha",
  "company": "Bank Alpha",
  "new_key": "mynewkey"
}
```

**Response `200`**
```json
{ "success": true, "message": "Key reset successfully." }
```

**Errors**
| Code | Reason |
|------|--------|
| 400 | Missing fields or key too short |
| 401 | Company name does not match |
| 404 | Node not found |

---

## Data

### `POST /upload`
Upload a CSV dataset for a node.
Uses `multipart/form-data` — not JSON.

**Form fields**
| Field   | Type | Description |
|---------|------|-------------|
| file    | File | CSV file to upload |
| node_id | str  | Registered node ID |

**CSV format required**
```
amount,time
5000,14:30
15000,02:00
```

**Response `200`**
```json
{
  "success": true,
  "message": "File uploaded for Bank Alpha. Call /analyze to process it.",
  "node_id": "alpha",
  "company": "Bank Alpha"
}
```

---

### `POST /analyze`
Run fraud detection on the most recently uploaded CSV for a node.
Raw amounts are never stored — only their SHA-256 hashes.

**Request**
```json
{ "node_id": "alpha" }
```

**Response `200`**
```json
{
  "success":     true,
  "company":     "Bank Alpha",
  "node_id":     "alpha",
  "total":       15,
  "fraud_count": 5,
  "safe_count":  10,
  "fraud_rate":  33.33,
  "message":     "Analysis complete for Bank Alpha"
}
```

**Errors**
| Code | Reason |
|------|--------|
| 400 | Missing node_id or required CSV columns not found |
| 404 | No uploaded file found for this node |
| 500 | CSV could not be parsed |

---

### `POST /clear_data`
Delete all transaction data for a node. Use before uploading fresh data.

**Request**
```json
{ "node_id": "alpha" }
```

**Response `200`**
```json
{ "success": true, "message": "Data cleared successfully" }
```

---

## Analysis

### `GET /results`
Per-node fraud summary. Optionally filter to one node.

**Query params**
| Param   | Required | Description |
|---------|----------|-------------|
| node_id | No       | Filter to a single node |

**Response `200`**
```json
{
  "success": true,
  "results": [
    {
      "company":     "Bank Alpha",
      "node_id":     "alpha",
      "total":       15,
      "fraud_count": 5,
      "safe_count":  10,
      "fraud_rate":  33.33
    }
  ]
}
```

---

### `GET /global_analysis`
Collaborative fraud detection across all nodes.

**Rules applied**
- Only data from the last 24 hours is considered
- Requires at least 2 nodes with submitted data
- Fraud rate > 5% → `FRAUD DETECTED`, otherwise `SAFE`
- Result is saved to case memory automatically

**Response `200`**
```json
{
  "success":       true,
  "node_count":    2,
  "total_records": 30,
  "total_fraud":   10,
  "total_safe":    20,
  "fraud_rate":    33.33,
  "decision":      "FRAUD DETECTED",
  "message":       "Global analysis complete across 2 nodes"
}
```

**Error `400`** — fewer than 2 nodes have submitted data
```json
{
  "success":    false,
  "node_count": 1,
  "message":    "Only 1 node(s) have submitted data in the last 24 hours. Minimum 2 required."
}
```

---

### `GET /logs`
Recent transaction activity for a node (hashed for privacy).

**Query params**
| Param   | Required | Description |
|---------|----------|-------------|
| node_id | Yes      | Node to fetch logs for |

**Response `200`**
```json
{
  "success": true,
  "logs": [
    {
      "company":      "Bank Alpha",
      "hash_preview": "d4c999ae4363...",
      "status":       "FRAUD",
      "timestamp":    "2024-01-01 14:30:00"
    }
  ]
}
```

---

### `GET /nodes`
All registered nodes and whether each has submitted data.

**Response `200`**
```json
{
  "success": true,
  "count":   2,
  "nodes": [
    {
      "node_id":  "alpha",
      "company":  "Bank Alpha",
      "joined":   "2024-01-01 10:00:00",
      "has_data": true
    }
  ]
}
```

---

### `GET /outcomes`
Past global fraud decisions (case memory). Returns last 10.

**Response `200`**
```json
{
  "success": true,
  "outcomes": [
    {
      "id":            1,
      "nodes":         ["alpha", "beta"],
      "total_records": 30,
      "total_fraud":   10,
      "node_count":    2,
      "decision":      "FRAUD DETECTED",
      "timestamp":     "2024-01-01 15:00:00"
    }
  ]
}
```

---

### `POST /discontinue`
Remove a node's data from the network. Account is kept — only transactions are deleted.

**Request**
```json
{ "node_id": "alpha" }
```

**Response `200`**
```json
{ "success": true, "message": "Connection discontinued and data cleared." }
```

---

## Report

### `GET /report`
Generate and download a PDF fraud detection report.
Includes global summary, per-node breakdown, and an AI narrative from Ollama (gemma4:e4b).

**Response** — `application/pdf` file attachment named `trustgrid_report.pdf`

> Requires at least one node to have submitted data.
> If Ollama is unavailable, the narrative falls back to a template string.
