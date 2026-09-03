v15.10 fast adaptive OCR
Happy path: one PaddleOCR call per frame.
DITV starts lower-left; Premiere Group/Insomnia/default starts upper-left.
Only if Paddle finds no text: wider same-corner crop, then Tesseract, then opposite corner.
Frames remain ~5/25/45 sec; no video frames or stream URLs are persisted.
