# Setup, do this before starting Claude Code

A short checklist to get the project ready on your Mac. Five minutes.

## 1. Put the files in place

You already have the three CSV exports in `treat-plumbing`. Move them into `data/raw/` so the folder is tidy:

```bash
cd ~/Documents/treat-plumbing      # adjust if your folder is elsewhere
mv *.csv data/raw/ 2>/dev/null || true
```

After unzipping this pack into `treat-plumbing`, the structure should look like the tree in the section below.

## 2. Python environment

```bash
python3 -m venv .venv
python3 -m venv .venvpython3 -m venv .venv
pip install anthropic pandas numpy
```

## 3. API key, kept local

Create a fresh key in the Anthropic Console at console.anthropic.com, Settings then API Keys. Before using it, set a low spend cap in the Console (Limits), say 20 dollars, so it cannot overspend. Then in your shell:

```bash
export ANTHROPIC_API_KEY=sk-ant-...your-key...
```

Do not paste the key into any chat. That is what got the last one disabled. Keeping it in the shell environment like this keeps it private.

## 4. Open it in Claude Code

Open the Claude desktop app, go to the Code tab, start a new session (Cmd plus N), and choose the `treat-plumbing` folder as the project. Claude Code reads `CLAUDE.md` automatically, so it starts with the full context.

## 5. A good first prompt

Something like:

> Read CLAUDE.md and the reference folder. I want to rebuild the pricing pipeline cleanly in src/, keeping the data findings and the classified data but treating the reference scripts only as a prior attempt to check against. Start by proposing the src/ pipeline structure and where you would improve on the reference, then wait for me before writing code.

## Target structure

```
treat-plumbing/
  CLAUDE.md                 standing brief, read every session
  SETUP.md                  this file
  .gitignore
  data/
    raw/                    the three AroFlo CSV exports
    classified/             class_jobs.json, class_quotes.json  (keep, expensive to regenerate)
  reference/                prior attempt, learn from or discard, do not inherit blindly
    treat-pricing-tool.html
    pricing_model.json
    pricing_model_v2.json
    scripts/
    docs/
  src/                      build the real pipeline here
  output/                   rebuilt models and tool land here
```

