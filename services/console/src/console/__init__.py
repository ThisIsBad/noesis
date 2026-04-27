"""Console — interactive recorded chat surface for the Noesis AGI stack.

Console wraps the eval harness's MCP-agent machinery to drive Claude
through all eight Noesis services from a browser chat box. Every
session is captured as a ``theoria.models.DecisionTrace`` and pushed
to Theoria's existing ``/api/traces`` endpoint, so the visualization
already understands the wire format.

The package is intentionally thin — it owns no business logic.
Sequencing belongs to Claude; semantics belong to the MCP services
(Praxis decomposes plans, Telos checks alignment, Logos verifies,
…). Console only does:

    1. accept a prompt over HTTP
    2. spawn Claude with the eight MCP servers wired
    3. translate the SDK message stream into incremental
       ``ReasoningStep`` updates
    4. push those updates to a per-session SSE bus
    5. POST the finalized ``DecisionTrace`` to Theoria when done

For the architectural framing of where Console fits alongside the
existing Claude Code dev loop and the eval-harness batch surface,
see ``docs/operations/console.md``.
"""
