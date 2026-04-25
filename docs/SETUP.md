# TrustGrid — Local Setup Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.10+ | Backend runtime |
| pip | any | Package installer |
| Ollama | latest | Local LLM for AI report narrative |

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/your-username/trustgrid.git
cd trustgrid
```

---

## Step 2 — Create a Virtual Environment (Recommended)

```bash
# Create
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate
```

---

## Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Step 4 — Install Ollama (for AI report narrative)

1. Download from **https://ollama.com** and install
2. Ollama starts automatically in the background after installation
3. Pull the model:

```bash
ollama pull gemma4:e4b
```

> If your machine has less than 7 GB of free RAM, use `gemma3:1b` instead
> and update `OLLAMA_MODEL` in `config.py`.

---

## Step 5 — Start the Backend

```bash
python app.py
```

You should see:

```
====================================================
  TrustGrid Backend  —  http://localhost:5000
====================================================
```

---

## Step 6 — Open the Frontend

Open `frontend/index.html` in your browser (Chrome or Edge recommended).

> If you see CORS errors, open the file via VS Code's Live Server extension
> instead of double-clicking.

---

## Step 7 — Test the System

### Register two nodes (in separate browser tabs)

**Tab 1 — Bank Alpha**
- Node ID: `alpha`
- Company: `Bank Alpha`
- Key: `secret123`
- Upload: `sample_data/sample_transactions.csv`

**Tab 2 — Bank Beta**
- Node ID: `beta`
- Company: `Bank Beta`
- Key: `secret456`
- Upload: `sample_data/sample_transactions.csv`

### Run Global Analysis

In either tab → Global Analysis → Run Global Analysis.

With 5 fraudulent rows out of 15 (33% rate) the decision will be
**FRAUD DETECTED**.

---

## Running Tests

```bash
pytest tests/ -v
```

All tests use a temporary database — your real data is never touched.

---

## Configuration

All settings are in `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `FRAUD_AMOUNT_THRESHOLD` | 10000 | Amount above which → fraud |
| `FRAUD_HOUR_THRESHOLD` | 5 | Hour before which → fraud |
| `FRAUD_RATE_THRESHOLD` | 5.0 | Global rate (%) above which → FRAUD DETECTED |
| `MIN_NODES_FOR_ANALYSIS` | 2 | Minimum nodes for global analysis |
| `DATA_WINDOW_HOURS` | 24 | How old data can be for global analysis |
| `OLLAMA_MODEL` | gemma4:e4b | LLM model for report narrative |
| `PORT` | 5000 | Backend port |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Address already in use` | Another process is using port 5000. Kill it or change `PORT` in `config.py` |
| `trustgrid.db` schema error | Delete `trustgrid.db` and restart — it will be recreated |
| Ollama error in report | Run `ollama list` to confirm `gemma4:e4b` is downloaded |
| CORS error in browser | Open frontend via VS Code Live Server |
| CSV column error | Ensure your CSV has columns named `amount` and `time` |
