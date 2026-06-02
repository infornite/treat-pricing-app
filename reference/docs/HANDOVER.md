# Treat Pricing, handover to finish offline

We hit a wall running the classification inside a chat: the API key, once pasted into the conversation, got disabled (almost certainly automated secret scanning). Nothing was lost. This pack lets you finish the job on your own machine, where the key stays private and the data lives with you. Below is exactly where we got to and exactly how to complete it.

## Where we got to

The pricing tool and the keyword based model are complete and working. On top of that we started upgrading the classifier from keyword matching to a comprehension pass, a language model that reads each narrative and returns structured fields (primary system, what was actually done, and a rich list of characteristics). That pass is part finished:

* 1,845 of about 4,900 reactive jobs classified (`class_jobs.json`)
* 45 of about 4,000 quotes classified (`class_quotes.json`)

These checkpoints are included, so finishing only does the remaining records, it does not redo these. Spend so far on your account was under about two dollars.

## What is in this pack

| File | What it is |
|---|---|
| `treat-pricing-tool.html` | The working tool. Open in a browser. Currently runs on the keyword model. |
| `pricing_model.json` | The complete keyword based model (the tool's current data). |
| `build_pricing_model.py` | Rebuilds `pricing_model.json` from the three CSVs. The reliable fallback. |
| `classify_run.py` | The comprehension classifier. Resumes from the checkpoints. |
| `classify_pilot.py` | Small sampler for spot checking quality and cost. |
| `class_jobs.json`, `class_quotes.json` | Classification done so far. Keep these so the run resumes. |
| `build_model_from_classification.py` | Builds the upgraded model from the classification. |
| `pricing_model_v2.json` | The upgraded model built on the partial classification so far (a preview). |
| `README.md` | How the model and the three layers work. |

## Finish it in four steps

You need Python with three packages and the three AroFlo CSV exports in the same folder.

```
pip install anthropic pandas numpy
# put jobs_jan23_to_jun26.csv, invoices_jan23_to_jun26.csv, quotes_jan23_to_jun26.csv here
export ANTHROPIC_API_KEY=sk-ant-...your-NEW-key...
```

1. Finish classifying the jobs (resumes at 1,845, Haiku, a few dollars):
   ```
   python3 classify_run.py jobs claude-haiku-4-5-20251001 class_jobs.json
   ```
   Run it again if it stops; it picks up where it left off. Repeat until it reports todo=0.

2. Finish classifying the quotes (resumes at 45, Sonnet for the richer read on the higher value half):
   ```
   python3 classify_run.py quotes claude-sonnet-4-6 class_quotes.json
   ```
   Same resume behaviour.

3. Build the upgraded model:
   ```
   python3 build_model_from_classification.py pricing_model_v2.json
   ```

4. Refresh the tool: open `treat-pricing-tool.html`, find the line beginning `const DATA =`, and replace the object after it with the contents of `pricing_model_v2.json`. Save. Done.

Rough total cost to finish: jobs about three to four dollars on Haiku, quotes about ten on Sonnet, so well under twenty dollars. Set a low spend cap on the new key first.

## What the upgrade changes

* Job type becomes the system the model read from the narrative (drainage, hot water, fixture, stormwater, and so on), not a keyword guess.
* Diagnosis only jobs are separated from real repairs. They are about 30 percent of reactive work and genuinely cheaper, and they become the lever that pulls a price down, which the old model never had.
* The characteristics are far richer: return or staged visits, building shutdown, multiple items, reinstatement (tiling, rendering, painting, waterproofing), structural works, large scope, and more, on both reactive and quoted work.
* Base figures are recency weighted, so the last year or so counts more than 2023, which matters because some types are up over twenty percent.

## A few honest notes

* `build_model_from_classification.py` is validated on the partial data and runs clean, but it has only ever seen 1,845 jobs and 45 quotes. Eyeball its output once the full classification is in, especially the quoted side, which is empty in the preview purely because so few quotes are classified yet.
* The classifier is first pass. The highest value thing you can still do is have Peter check a sample of the structured output and correct any systems or characteristics that read wrong, then rerun the build.
* If confidentiality of client or strata narratives matters, remember the classification sends those narratives to the API under your account. Worth a check against your data handling obligations before the full run.
* Keep the new key out of any chat or shared doc. Run it locally as above.
