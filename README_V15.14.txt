v15.14 — lightweight verification of EPG that already exists

Separate workflow: Verify Existing Movie EPG.

It checks ONLY movie channels whose movie_epg_audit status is currently OK.
Default load is intentionally small:
- 6 channels per run;
- one frame around second 6;
- 2 capture workers;
- hard workflow timeout 18 minutes;
- rotating persistent cursor so the next run continues with the next channels.

The OCR title is compared with the XMLTV programme that is current at the
moment of the screenshot.

VERIFIED: titles match after normalization/fuzzy comparison.
MISMATCH_PENDING: first disagreement.
MISMATCH_CONFIRMED: the same EPG title / OCR title disagreement was seen twice.
NO_CONFIDENT_OCR / CAPTURE_FAILED do not penalize the EPG source.

Confirmed mismatch can temporarily replace the visible current programme via
the existing OCR overlay. A single screenshot can never override a valid EPG.
