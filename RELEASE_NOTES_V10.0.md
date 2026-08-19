# v10.0 — Movie metadata coverage + descriptions

## Main fixes

- Metadata budget now counts **unique canonical titles**, not individual TMDb HTTP calls. A single difficult title can no longer burn several budget units.
- Workflow budget raised to **20,000 unique titles** and job timeout to **90 minutes**.
- Channels in `Кино`, `Кино 4K`, `Кинозалы`, and `Кинозалы UA` are processed first for metadata enrichment.
- TMDb genres are added as XMLTV `<category lang="ru">` values.
- When the provider has no useful description, TMDb overview is inserted into `<desc>`. Russian overview is preferred; English is used as fallback when Russian is unavailable.
- User-facing description format is now: `Жанр → описание → IMDb rating/votes`. The technical IMDb `tt...` ID is kept only in the `<url>` field, not in the visible description.
- Existing useful provider descriptions are preserved rather than replaced.
- v9.1 precision safeguards for transliteration, sequel numbers, dotted series titles, and legacy-cache revalidation remain enabled.

## Expected UHF display

Example:

```text
Жанр: боевик, комедия, триллер.
Телохранитель Майкл Брайс снова оказывается втянут в опасную авантюру...
IMDb 6.1/10 · 123 456 голосов
```

## Install

Upload the full contents of this archive over the repository, preserving `.github/workflows/update.yml`, then run **Update EPG** manually once. The first v10 run may be longer because metadata cache schema is bumped to 11.
