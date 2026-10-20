# AlphaEvolve local evaluator interoperability

This is the evaluator-contract slice of [#468](https://github.com/algorithmicsuperintelligence/openevolve/issues/468).
It runs the **unchanged** `program.py` and `evaluate.py` from Google's
[AlphaEvolve examples](https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud)
through an explicit adapter. A separate opt-in helper imports a limited subset
of an experiment configuration for local Python runs. Neither helper replaces
the cloud SDK, exports bundles, or implements all of #468.

## Evaluate an upstream seed locally

From an installed OpenEvolve checkout:

```bash
git clone https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud.git ../alphaevolve-reference

# Evaluator-only dependencies; no Google client or authentication is used.
python -m pip install numpy scipy matplotlib pydantic
export PYTHONPATH="$(cd ../alphaevolve-reference/src && pwd)${PYTHONPATH:+:$PYTHONPATH}"
export MPLBACKEND=Agg

python examples/alphaevolve_interop/run.py ../alphaevolve-reference/examples/circle_packing
python examples/alphaevolve_interop/run.py ../alphaevolve-reference/examples/tsp
python examples/alphaevolve_interop/run.py ../alphaevolve-reference/examples/signal_processing
```

Without `--config`, the runner only evaluates the seed and prints metrics and
artifacts. It makes **no LLM or Google Cloud requests**. The `alpha_evolve.models`
import used by circle packing resolves to the upstream source, not a fake SDK.
Upstream example dependencies can change; inspect their requirements if an import
fails. The signal-processing evaluator writes its normal `programs/` artifacts
under the current directory, so run it in a disposable working directory if needed.

To generate and evaluate new candidates, provide **your own OpenEvolve config**:

```bash
python examples/alphaevolve_interop/run.py ../alphaevolve-reference/examples/circle_packing \
  --config /path/to/your-openevolve-config.yaml --iterations 1 --output-dir ./interop-output
```

This second command invokes the model/provider you configured and may incur API
charges. It does not use or translate the Google example's `.env`, cloud client,
`run_evolution.py`, or Google credentials. Local model endpoints work as with any
other OpenEvolve run. Remote Cloud Run/GKE evaluators are not supported here.

## Use the adapter directly

```python
from openevolve.compat.alphaevolve import adapt_evaluator

# imported_evaluator is the original synchronous AlphaEvolve evaluator callable.
evaluate = adapt_evaluator(imported_evaluator, objective_metric="sum_of_radii")
```

Use `evaluate` with `run_evolution(..., evaluator=evaluate)`, or expose it in an
evaluator module for the CLI. The helper:

- Reads the candidate's source file as UTF-8 and constructs
  `{"content": {"files": [{"path": filename, "content": source}]}}`.
- Accepts the nested `scores.scores` / `insights.insights` envelope as dictionaries
  or SDK-style objects, without importing Google's package in OpenEvolve.
- Keeps all metrics for features and maps the explicitly selected objective to
  `combined_score`, avoiding accidental averaging of unrelated metrics.
- Stores insights as JSON in the `alphaevolve_insights` artifact.
- Marks exact `-1e12` sentinel, null, and non-finite scores as failures, with
  `error: 0.0`, an error artifact, and a `combined_score` of `-1e12`. This avoids
  giving a failed candidate zero fitness when valid objectives are negative.

The sentinel is an example convention, not a universal SDK rule. Set
`failure_sentinel=None` to disable it or choose a different sentinel. Choose a
finite `failure_score` **below every valid score** for your problem. A failed
secondary metric also marks the whole evaluation failed. Duplicate metrics,
missing objectives and malformed scores raise actionable errors. The names
`error` and `combined_score` are reserved by this mapping; select
`objective_metric="combined_score"` if that is already your original metric.

Exceptions propagate to OpenEvolve's existing retry/error handling. That generic
handling may return zero fitness on exceptions or timeouts; this adapter does not
change that behavior. For negative objectives, inspect error/timeout results
before interpreting the best program.

The adapter provides **no sandbox**. Like the original local evaluators, it runs
trusted Python code with the current process's privileges. Use a separate
execution environment for untrusted candidates.

## Import a local Python experiment configuration

`config_from_alphaevolve` imports an explicit experiment dictionary without
reading `.env`, contacting Google, or creating model clients:

```python
from openevolve.compat.alphaevolve import config_from_alphaevolve

experiment = {
    "title": "Circle Packing",
    "program_language": "python",
    "problem_description": "Pack circles into a unit square.",
    "run_settings": {"max_programs": 10},
    "generation_settings": {
        "models": [{"name": "my-local-model", "weight": 1}],
    },
}
config = config_from_alphaevolve(
    experiment,
    api_base="http://localhost:8000/v1",
    api_key="local-placeholder",  # Replace if the chosen endpoint requires authentication.
)
# Pass config to run_evolution(program_path, adapted_evaluator, config=config).
# Running evolution invokes your chosen endpoint; conversion alone does not.
```

The imported names must be served by the explicitly supplied OpenAI-compatible
endpoint. Gemini model names are not remapped to local models. Endpoint/key
values embedded in the cloud dictionary are never copied. A missing `api_key`
retains OpenEvolve's usual provider behavior, which may use `OPENAI_API_KEY` when
the client is subsequently constructed. Conversion adds no Google dependency.
For a Google SDK config object, pass its `model_dump()` dictionary.

| AlphaEvolve field | OpenEvolve mapping |
| --- | --- |
| `generation_settings.models[].name/weight` | `llm.models`, with relative weights unchanged; null/missing weights become 1 |
| `run_settings.max_programs` | `max_iterations`, requiring an explicit positive integer |
| `problem_description` + optional `generation_settings.context` | Literal `prompt.system_message` text |
| `program_language="python"` | `language="python"`, `.py` suffix |

The converter disables cascade evaluation for the single-stage local evaluator;
other OE settings retain their defaults. It does not mutate the input or start
a run. Missing models, missing budgets and unsupported languages raise instead
of guessing defaults. `title` is metadata and is not imported.

`max_iterations` counts generation attempts, **not** successful evaluations,
requests, tokens or money. OE also evaluates the initial seed, and retries can
make additional calls. `run_settings.max_duration` is rejected because this
helper cannot enforce that wall-clock limit. Non-null unsupported settings emit
warnings naming the fields, including cloud `concurrency`, prompt-inclusion
flags and evolution settings. Their semantics are not silently presented as
equivalent OE controls; OE's worker count stays at its default of one unless
you configure it separately. Model-specific extra fields also warn and are not
forwarded. Warning messages include field paths, not their values.

The dictionary helper provides a subset of inbound configuration support (A3
in #468). It does not read `.env` files, emulate the experiment/controller SDK,
or export cloud-compatible bundles. Use the returned `Config` directly with
the Python API; explicit `.env` import is described below.

## Import an explicit example .env file

Install the optional parser (the base OpenEvolve install is unchanged):

```bash
python -m pip install "openevolve[alphaevolve-env]"
# From a source checkout: python -m pip install -e ".[alphaevolve-env]"
```

```python
from pathlib import Path
from openevolve.compat.alphaevolve_env import config_from_alphaevolve_env

config = config_from_alphaevolve_env(
    "../alphaevolve-reference/examples/tsp/example.env",
    problem_description=Path(
        "../alphaevolve-reference/examples/tsp/instructions.md"
    ).read_text(encoding="utf-8"),
    api_base="http://localhost:8000/v1",
    api_key="local-placeholder",
)
# Pass config to run_evolution with the original seed and adapted evaluator.
# Importing alone does not construct clients or call the endpoint.
```

Only the named file is read. The helper does not find a default `.env`, read
other environment variables to fill missing settings, interpolate variable
references, change `os.environ`, or execute shell commands or the original
`run_evolution.py`. The problem text and OE endpoint/key remain explicit caller
arguments. A missing `api_key` still allows OE's usual provider behavior when
a model client is later constructed, as described above.

| .env setting | Mapping / behavior |
| --- | --- |
| `MODEL`, optional `MODEL_WEIGHT` | Single model; missing weight becomes 1 |
| `MODEL_1..N`, optional `MODEL_i_WEIGHT` | Weighted model list in numeric index order; gaps allowed |
| `MAX_PROGRAMS_GENERATED` | Required positive integer mapped to `max_iterations` |
| `MAX_PROGRAMS_EVALUATED` | If present, must equal the generation budget; always warns that it is not a hard evaluation cap |
| Other non-null variables, including cloud credentials/endpoints and concurrency | Not imported; warnings contain names, not values |

Either model form may be used, but not both. Empty names, orphan weights,
non-positive/non-finite weights, duplicate assignments, malformed syntax and
variable/command references in model names raise errors. Quoting, comments,
`export` prefixes and multiline quoted values are parsed with `python-dotenv`;
expansion is intentionally disabled. No model names are guessed or remapped.
Some upstream examples, including signal processing, do not declare models in
their `example.env`: add an explicit model or use the dictionary helper instead.

An evaluation-only budget, or different generation and evaluation budgets,
is rejected rather than translated into an allegedly equivalent limit. Even
equal budgets are not equivalent: OE counts generation attempts, additionally
evaluates the seed, and may retry. This helper does not impose a strict
evaluation, request, token, time or cost limit. The existing dictionary helper
performs the final configuration validation; existing config loading and the
example command-line runner are unchanged.

## Validation

Default unit tests use synthetic envelopes and OpenEvolve's real evaluator and
callable-serialization path, without Google's SDK, keys, or network access:

```bash
python -m unittest discover -s tests -p test_alphaevolve_compat.py
python -m unittest discover -s tests -p test_alphaevolve_config.py
python -m unittest discover -s tests -p test_alphaevolve_env.py
```

The walkthrough additionally permits direct validation against an upstream
checkout. An evaluator-only run demonstrates contract compatibility, not learned
improvement or a real-model evolution experiment.
