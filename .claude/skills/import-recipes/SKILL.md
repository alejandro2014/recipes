---
name: import-recipes
description: Batch-import recipes from a plain text file with one recipe URL per line, running the import-recipe skill for each. Use when the user gives a file of recipe URLs to add.
argument-hint: <file with urls>
---

Import every recipe listed in the file $ARGUMENTS, one URL per line, using the `import-recipe` skill for each.

## 1. Read the list

- Read the file. Ignore blank lines and lines starting with `#`; trim whitespace.
- Drop duplicate URLs, and any line that is not an `http(s)://` URL (report those as invalid at the end).
- If the file doesn't exist or has no URLs, stop and tell me.

## 2. Import each URL

Import each URL in its own subagent (Agent tool, `general-purpose`), so each import's page fetches and file reads stay out of this conversation. Launch up to 4 at a time, wait for them to finish, then launch the next group, until every URL is done. If a subagent fails or returns nothing usable, record that URL as `error` and go on. Never let one URL abort the batch.

Give each subagent this prompt, with `<url>` replaced:

> Import the recipe at <url> into the recipe collection in this repository by invoking the `import-recipe` skill with the URL as its argument and following its instructions, with these overrides because this is an unattended batch import:
>
> - Don't stop to ask anything. If the recipe already exists (`RecipeExistsError`), don't overwrite it.
> - If the page fails (fetch error, no recipe, paywall/login), stop and report the reason.
> - Still do the round-trip check of step 4, but don't print the full markdown file.
> - Don't commit and don't touch any other recipe.
>
> End your reply with exactly these lines:
>
> ```
> RESULT: importado | ya existía | error
> SLUG: <slug, or the existing slug, or empty>
> REASON: <error reason, or empty>
> NOTES: <conversions, translations and assumptions made, in one short paragraph>
> ```

Collect the `RESULT`/`SLUG`/`REASON`/`NOTES` of each subagent for the report.

## 3. Report

At the end, give me a summary table with one row per URL: URL, result (`importado`, `ya existía`, `error`, `inválida`), slug or reason. Below it, list the notable conversions/assumptions per imported recipe, and the URLs I should retry or check by hand.
