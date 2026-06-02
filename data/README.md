# Data

## raw/
The three AroFlo report exports, January 2023 to June 2026. Join key is `Jobnumber`.

* `jobs_jan23_to_jun26.csv`, completed jobs. Price is `Task Invoices Total Ex`, work narrative is `Invoice Description`, short descriptor is in `Task` after the last " - ".
* `invoices_jan23_to_jun26.csv`, invoice line items, joins to jobs on `Jobnumber` at about 99.6 percent. Named add on rates in `Inv Item Description` and `Inv Line Unit Sell`.
* `quotes_jan23_to_jun26.csv`, quotes, several rows per quote with the total repeated. Scope is `Task Description`, status is `Status`.

This is client and strata data. Keep it private. The default .gitignore does not commit it.

## classified/
Structured fields produced by the comprehension classifier, keyed by job number. KEEP THESE, regenerating them costs API money and time.

* `class_jobs.json`, 1,845 of about 4,900 reactive jobs done.
* `class_quotes.json`, 45 of about 4,000 quotes done.

The classifier resumes from these, so finishing only does the remainder.
