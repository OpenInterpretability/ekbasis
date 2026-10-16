# Skopos image check (pre-registration, 2026-10-15 19:24 UTC, before any image answer)

The state can be text or an image in Ekbasis-27B; Skopos' last training (R4) was text only (the vision tower is
untouched, but the language layers it feeds changed). Items: the worlds and drawings of conseq/image_eval.py (lamps as
bulbs, containers with the water level; 1–3 actions), seed 'image-fresh-20261015', 200 per world (400 items), half with
an answer the actions change. Three prompts per item: text, image (state as an image), read (final state as an image).
Models: Ekbasis-27B-INT4 (public) and Skopos INT4, both through serve.py + vLLM on the same RTX, images sent in the
request as a client does (`image_served.py`).
Reading (paired bootstrap by item, 2,000, seed 20261015): image ability is **preserved** if Skopos − Ekbasis-27B is
≥ −2.0 points on the image prompts and on the read prompts (all items). Text and the changed-answer subsets reported.
Informs the release (as image did for the first Skopos); does not block it on its own.
