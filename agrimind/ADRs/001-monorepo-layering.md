# ADR 001: Monorepo with Strict Layering

## Status
Accepted

## Context
AGRIMIND requires a scalable, maintainable architecture that prevents import cycles, enforces separation of concerns, and enables independent evolution of components. The system spans multiple layers from zero-dependency contracts to full microservices.

## Decision
We will use a monorepo structure with strict layering enforced by import rules:

```
Layer 0: kernel (contracts, config, errors, telemetry) - ZERO dependencies on other packages
Layer 1: data-kernel (lakehouse contracts, dataset manifests, tokenizer manifests)
Layer 2: memory (graph, vector, retrieval contracts)
Layer 3: models (inference contracts, model registry)
Layer 4: agents (LangGraph nodes, tools, safety)
Layer 5: services (FastAPI services, workers)
Layer 6: apps (gateway, expert-console, admin)
```

### Import Rules
- Lower layers can be imported by higher layers
- Higher layers CANNOT be imported by lower layers
- No circular imports allowed
- `kernel` package must have ZERO external dependencies beyond Python stdlib and Pydantic

### Enforcement
- Use `import-linter` in CI to enforce layer boundaries
- Use `mypy` for type checking across layers
- Use `ruff` for linting and import sorting
- Pre-commit hooks prevent violations before commit

## Consequences

### Positive
- Clear separation of concerns
- Prevents architectural drift
- Enables independent testing of layers
- Makes dependency graph explicit
- Facilitates code reuse across services

### Negative
- Requires discipline to maintain
- May feel restrictive initially
- CI checks add time to PR workflow

### Mitigation
- Automated enforcement in CI
- Clear documentation of layer responsibilities
- Architecture review for boundary changes

## References
- Clean Architecture by Robert C. Martin
- Domain-Driven Design by Eric Evans
- Google's Software Engineering practices
