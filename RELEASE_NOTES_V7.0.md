# v7.0

- TMDb remains the primary RU/EN fiction title resolver.
- IMDb ID becomes the stable metadata identity.
- IMDb rating + vote count are fetched directly from IMDb title-page structured data.
- OMDb is optional fallback only when direct IMDb metadata has neither rating nor votes.
- New persistent IMDb entity cache keyed by IMDb ID.
- 30-day refresh for rating/votes; 7-day retry for missing data.
- Existing canonical series memo/cache remains: 120 episodes do not trigger 120 title searches.
- v6 positive title mappings migrate safely; stale negative caches are not trusted.
- metadata report now includes `imdb_votes`.
- Kinopoisk is intentionally not integrated.
