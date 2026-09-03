v15.12 confidence/garbage filter
- rejects OCR noise before it can become last_title
- keeps legitimate short titles such as ИГРА, ОГОНЬ and Горько
- filters mixed-script garbage and punctuation-heavy fragments
- only medium/high-confidence titles train zone/engine/history
- old learned garbage is cleared automatically when profiles are loaded
