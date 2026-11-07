# Architecture

Synthetic data. One Vultr Cloud Compute VM runs everything in Docker Compose (`compose.yml`); the model is Vultr Serverless Inference.

## Deployment on Vultr

```mermaid
flowchart TB
  U["Judge's browser"] -- HTTPS --> CADDY
  subgraph VM["Vultr Cloud Compute VM · vhf-3c-8gb · ewr · Ubuntu 24.04 · ufw 22/80/443"]
    CADDY["caddy:2<br/>Let's Encrypt via sslip.io<br/>only service with ports"] --> APP
    APP["app (FastAPI + htmx, 1 uvicorn worker)<br/>core gate · agent client · writer"]
    MIG["migrate (one-shot)<br/>schema + roles + passwords"] --> DB
    APP -- "cg_writer: INSERT only" --> DB[("postgres:16<br/>no published port<br/>append-only triggers")]
    APP -- "cg_reader: SELECT only" --> DB
    APP --- VOL[("appvar volume<br/>trick-attempt log")]
  end
  APP -- "HTTPS, VULTR_INFERENCE_KEY" --> SI["Vultr Serverless Inference<br/>glm-5.3-flash"]
```

## Data flow of one close

```mermaid
sequenceDiagram
  participant M as core.matcher
  participant A as agent (glm-5.3-flash)
  participant G as core.gate (rules 1-12)
  participant H as Approver (controller/CFO)
  participant S as core.sod (13-14)
  participant W as writer (cg_writer)
  participant R as verify (cg_reader)
  participant C as hash chain
  M->>G: 77 deterministic proposals
  M->>A: 3 unmatched lines + free candidate invoices (memo = untrusted data)
  A->>G: JSON proposal (txn, invoices, amount, parts)
  G->>C: every decision with rule id
  G-->>H: allowed / amber-flagged lines only
  H->>S: approve (name, role, memo ack)
  S->>C: approval or refusal
  S->>W: post only with a valid approval
  W->>R: rows written
  R->>C: read-back count + row hashes match?
```

## Trust boundaries
- **Model output is untrusted.** It can only propose ids and amounts; rules 2, 3, 10 and 11 check them against the CSV rows.
- **Memo text is untrusted.** It is shown to the model as data and checked by rule 12 (tripwire + flag), but it can never change a number or an approval.
- **Approval is human and named.** Rule 13 refuses the proposer or a non-approver role; rule 14 refuses a post without approval.
- **Storage is append-only.** Triggers block UPDATE/DELETE/TRUNCATE for every role; tampering is caught by hash recompute (`tests/test_writer.py`).
- **Gap:** the agent client and the writer run in one process/container; isolation is by code, not by network.
