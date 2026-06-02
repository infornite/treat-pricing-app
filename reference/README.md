# Reference, a prior attempt

Everything in here was built in an earlier exploratory session. It is here to LEARN FROM or DISCARD, not to inherit as a foundation. The findings it is based on are captured in the project CLAUDE.md and are worth keeping. The specific code and category choices are provisional and were made under time pressure, so check them, do not trust them blindly.

## What is here

* `treat-pricing-tool.html`, the working tool from that session. Open it in a browser or the Claude Code preview to see the three layer model in action. Its data is embedded in the `const DATA =` block.
* `pricing_model.json`, the model data built with the older KEYWORD classifier. Complete, but the classifier is the weak part.
* `pricing_model_v2.json`, a preview of the model built from the newer COMPREHENSION classifier, on partial data only (1,845 jobs, 45 quotes), so the quoted side is thin.
* `scripts/`
  * `build_pricing_model.py`, builds the keyword model from the CSVs.
  * `classify_run.py`, the comprehension classifier with checkpoint and resume. Reads a key from an env var if you adapt it (it originally read from a local file).
  * `classify_pilot.py`, small sampler for spot checking classification quality and cost.
  * `build_model_from_classification.py`, builds the upgraded model from the classified fields, with recency weighting and diagnosis only as a downward lever.
* `docs/`
  * `model-notes.md`, how the model and the three layers work.
  * `HANDOVER.md`, the step by step to finish the classification, written when the work moved offline.

## Known weaknesses to fix when rebuilding

* The keyword classifier picks the first matching word and about 93 percent of narratives match several types, so it is fragile. The comprehension pass is the intended replacement.
* Category names and keyword lists were first pass.
* Scripts read input from the directory they were run in. If you reuse any, fix the paths to point at `../data/raw` and `../data/classified`.
* The classified data those scripts produced lives in `data/classified/`, keep it, it costs money to regenerate.
