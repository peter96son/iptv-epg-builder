v15.11 learning OCR profiles

Adds persistent output/movie-gap-ocr-profiles.json.

Per channel the verifier learns:
- preferred OCR zone;
- preferred OCR engine;
- last recognized movie title;
- short title history;
- static text/logos to ignore.

Channel/provider names are filtered from title candidates.
Other OCR text is promoted to static_text only after co-occurring with at least
3 distinct recognized movie titles, reducing the risk of classifying a long
movie title as a permanent logo.

The hourly workflow commits both the current OCR result and the learned profile,
so the next run starts directly in the previously successful corner/engine.
