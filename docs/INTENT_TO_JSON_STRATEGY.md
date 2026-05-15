# Intent-To-JSON Strategy

SW Copilot succeeds only when user intent is compiled into a small, validated
JSON contract before SolidWorks is touched. Provider choice can improve planner
quality and quota resilience, but it cannot fix an invalid coordinate contract,
face selector, or executor semantic mismatch.

## Product Rule

Every supported feature family gets this pipeline:

`prompt -> DesignSpec -> CoordinatePlan -> SketchGraph -> OperationGraph -> PartReport -> ValidationReport -> run trace`

The LLM may help only at the `prompt -> DesignSpec` boundary for unsupported or
ambiguous language. Deterministic code owns coordinates, standards, sketch
entities, operation ordering, and validation.

## Why The Base-Plate Live Test Failed

The failed base plate was not a Groq failure. The deterministic parser produced
the intended JSON, but the plane contract was wrong for SolidWorks:

- SolidWorks `Top Plane` is not the XY plane for this execution target.
- The generated plate stood on edge (`120 x 10 x 80`) instead of lying in XY
  with Z thickness (`120 x 80 x 10`).
- Hole circles were created in sketch space, but the selected face/plane was not
  the intended top surface for the plate contract.

The correct response is to fix the IR-to-executor contract and add regression
tests, not to switch LLM providers.

## Evaluation Before Expansion

Before adding more CAD families, create a golden intent corpus:

- `prompt`
- expected `DesignSpec`
- expected `CoordinatePlan`
- expected `SketchGraph`
- expected `OperationGraph`
- mocked `PartReport`
- expected `ValidationReport`

Minimum first corpus:

- 50 base-plate prompt variants
- 50 box/block/cube variants
- 50 cylinder/shaft variants
- 50 hole-pattern variants that require clarification or deterministic layout
- 25 delete/undo/cleanup variants
- 25 negative prompts that must return unsupported or clarification

No prompt family graduates to SolidWorks live testing until its JSON artifacts
pass offline tests.

## Dataset Use

External CAD datasets and papers should be used to improve the intent compiler
and eval corpus, not as runtime truth. Runtime dimensions still come from
deterministic standards tables and validated geometry code.

Use public datasets for:

- common feature sequence patterns
- naming and synonym coverage
- prompt paraphrase generation
- OperationGraph examples
- model comparison and fine-tuning after evals exist

Do not use datasets for:

- exact ISO/ASME dimensions at runtime
- directly replaying unknown CAD scripts in SolidWorks
- bypassing the OperationGraph schema

## Provider Policy

Provider routing is now a planner backend detail:

- deterministic paths run with no provider
- NIM, Groq, and Ollama may be benchmarked on the same golden corpus
- the winner is the model with the highest exact JSON pass rate, not the most
  fluent explanation
- provider errors must fail safely before SolidWorks execution

Switching from Groq to NIM is reasonable for quota/model benchmarking, but it is
not a substitute for the intent-to-JSON eval layer.
