# CODER_RULES.md

You are implementing the Coordinated Fresh Capital Flow Strategy MVP.

Follow these rules strictly.

## General principles

- Build only what the current step requires.
- Do not add extra features, abstractions, services, or infrastructure.
- Keep the implementation deterministic, minimal, readable, and testable.
- Prefer simple code over clever code.
- Preserve provider-agnostic design.
- Do not add network calls, live integrations, external APIs, databases, or background workers unless the current step explicitly requires them.
- Do not add UI, dashboards, Telegram bots, or deployment logic unless explicitly required.
- Do not rewrite previous working modules unless necessary for the current step.

## Code style

- Use Python.
- Prefer standard library unless a dependency is clearly necessary.
- Use type hints everywhere practical.
- Prefer frozen dataclasses for immutable domain objects.
- Keep functions small and focused.
- Avoid hidden side effects.
- Avoid global mutable state.
- Use explicit names; avoid vague names like `data`, `obj`, `thing`, `process_stuff`.
- Keep modules narrowly scoped.

## Project structure

- Put source code under `src/`.
- Put tests under `tests/`.
- Keep config/constants separate from domain models and business logic.
- Keep step outputs aligned with existing folder structure.
- Do not move or rename files unless necessary.

## Validation and domain discipline

- Validate inputs close to the domain boundary.
- Fail loudly on invalid input.
- Prefer explicit validation helpers over implicit assumptions.
- Keep time handling explicit and consistent.
- Do not silently coerce incorrect values unless the step explicitly allows it.
- Enums and thresholds must remain stable and easy to inspect.

## Testing rules

- Every implemented step must include tests.
- Add only the tests needed for the current step.
- Cover happy path plus core failure/edge cases.
- Keep tests deterministic.
- Do not rely on internet access, real services, wall-clock timing, or random nondeterministic behavior.

## Scope control

- If the prompt asks for a foundation layer, implement only the foundation layer.
- If the prompt asks for one classifier, implement only that classifier.
- Do not prematurely implement later pipeline stages.
- Do not add persistence/artifacts unless explicitly requested in the step.

## Delivery format

After finishing each step, always report:

1. Files created/changed
2. What was implemented
3. Exact commands to run tests
4. Assumptions or blockers

## Safety / change discipline

- Work only inside this repository.
- Before editing, inspect the current repo structure.
- Preserve compatibility with existing Step 1 code unless the current step explicitly requires a change.
- If something is ambiguous, choose the smallest safe implementation that satisfies the prompt.nano docs/CODER_RULES.md
