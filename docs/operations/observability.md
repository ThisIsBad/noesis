# Observability — current state, gaps, and forward path

> **Status: 2026-04-23.** Written as part of the Tier-3 action list in
> [architect-review-2026-04-23.md](../architect-review-2026-04-23.md).

## What actually happens today

Every service calls `get_tracer()` at module load, which returns a
`KairosClient` from `kairos/src/kairos/client.py`. Inside each MCP
tool handler:

```python
with get_tracer().span("store_memory", metadata={"id": mem.id}):
    ...
```

The tracer HTTP-POSTs a `noesis_schemas.TraceSpan` JSON blob to the
Kairos service (env var `KAIROS_URL`, e.g.
`https://kairos-production.up.railway.app`). Kairos stores the span
**in memory** (`KairosCore._spans: list[TraceSpan]`). That's the whole
pipeline.

```
[service]  ──(HTTP POST /spans/record)──▶  [Kairos]  ──▶  list in RAM
```

## What we don't have

- **No OTLP export.** Kairos lists
  `opentelemetry-exporter-otlp>=1.24` as a dependency but never
  actually constructs a `TracerProvider`, `BatchSpanProcessor`, or
  `OTLPSpanExporter`. The OTEL deps are unused.
- **No receiver.** Kairos's HTTP surface is a custom JSON API, not
  OTLP / gRPC.
- **No persistence.** A Kairos restart loses every trace. There is no
  disk or database backing.
- **No UI.** `kairos.query_spans` returns JSON; there is no Jaeger /
  Tempo / Honeycomb dashboard.
- **No sampling.** 100 % of spans are emitted.

None of this is a defect of the current code — it's a deliberate v1.
But the architecture doc gives the impression that Noesis has "real
observability", and the reality is closer to "an in-process span
store with OTEL-shaped types".

## Short-term recipe (local dev)

Until we move to real OTLP, the fastest way to visualise what's
happening in a Kairos run is to hit Kairos directly:

```bash
# List recent spans
curl -s https://$KAIROS_URL/spans/recent?limit=50 | jq .

# Spans for a specific trace_id
curl -s https://$KAIROS_URL/traces/<trace_id> | jq .
```

[Theoria](../../ui/theoria/README.md) already has a `live fetch`
endpoint (`GET /api/kairos/traces/{trace_id}`) that pulls from Kairos
on demand and renders the span tree as a reasoning DAG. That's the
closest thing to a dashboard we have today — use it.

## Forward path — when we're ready

The pragmatic promotion is a **two-stage pipeline**:

```
[service]
    │
    │   (OTEL SDK in-process BatchSpanProcessor)
    ▼
[OTLP collector: otel-collector or Jaeger all-in-one]
    │
    │   (fan-out)
    ├──▶  Jaeger UI            (local dev dashboard)
    ├──▶  Kairos JSON API      (programmatic query, Theoria,
    │                           eval-time assertions)
    └──▶  (optional) Honeycomb  (production SaaS dashboard)
```

### Code changes required

1. **In each service's `tracing.py`** — construct a real
   `TracerProvider` with a `BatchSpanProcessor` fed by
   `OTLPSpanExporter`. Read the exporter endpoint from
   `OTEL_EXPORTER_OTLP_ENDPOINT` (standard env var; default
   `http://localhost:4317`). Keep the `KairosClient.span()` context
   manager as a thin wrapper that also pushes to the OTEL tracer.
2. **In Kairos** — wire a tracer endpoint that ingests OTLP/HTTP and
   persists to the same in-memory store (or upgrade the store to
   SQLite while we're at it — see Tier 3 persistence consolidation).
   Keep the existing `/spans/record` JSON endpoint for callers that
   don't yet use the SDK.
3. **Optionally** — make Kairos emit to an upstream OTLP collector
   for fan-out. This lets ops attach Honeycomb / Datadog without
   touching service code.

### Local dev recipe

A one-file compose for developers who want a dashboard now, even
before the code changes above land. Put this at the root of the
repo (or under `docs/operations/`) and run `docker compose up`:

```yaml
# docker-compose.observability.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.57
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
```

Then, in any service, set:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Jaeger UI at `http://localhost:16686` will show traces as soon as
the services are OTEL-wired. Until they are, this is just scaffolding.

## Decision to make

There's a genuine fork here. Three viable shapes:

1. **Keep Kairos custom.** Current path. Works, dev-friendly, fits
   the ecosystem's Greek-named-service aesthetic. Doesn't integrate
   with any external tooling. Fine for phase 1; insufficient once
   the system grows past ~10 services or needs ops dashboards.
2. **OTLP collector + Kairos as downstream consumer.** Services emit
   OTLP; an external collector fans out to Jaeger + Kairos + any
   SaaS. Kairos becomes an analytical layer on top, not the
   primary sink. Most standards-compliant.
3. **Kill Kairos, adopt a commodity stack.** OTLP collector + Jaeger
   + SQL warehouse. Less bespoke, more ecosystem tooling, loses the
   "trace-linked decision view" coupling with Theoria.

**Recommendation: option 2.** Keeps the Theoria integration story
intact (Theoria still fetches from Kairos's JSON API), adds
standards compliance so ops tooling plugs in, and doesn't throw away
the existing `KairosClient.span()` ergonomics that services already
depend on. Effort: a few hundred lines across `kairos/` and the
service `tracing.py` modules. Mostly plumbing, no redesign.

**Not part of Tier 3 follow-through.** This is a roadmap item, not a
this-week task — put it on the next architectural milestone.
