# Vocabulary engine

Vocabulary is user-owned and advances only from an explicit observation. Its ordered states are:

`Encountered -> Recognized -> Recalled -> Spoken -> Used correctly -> Used naturally -> Used spontaneously`

A single observation may advance a word, but it cannot regress it. “Used naturally” and “Used spontaneously” are normally retained as mastery evidence rather than selected for deliberate practice.

For a challenge, V1 chooses up to three in-progress terms. It ranks topic matches first, then terms at retrieval stages (especially Recalled and Spoken), then least recently updated terms, with ID as the deterministic tiebreaker. A challenge can reference vocabulary, but V1 does not make unencountered vocabulary a hidden requirement.
