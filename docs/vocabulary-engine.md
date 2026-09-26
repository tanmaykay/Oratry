# Vocabulary engine

Vocabulary is user-owned and advances only from an explicit observation. Its ordered states are:

`Encountered -> Recognized -> Recalled -> Spoken -> Used correctly -> Used naturally -> Used spontaneously`

A single observation may advance a word, but it cannot regress it. “Used naturally” and “Used spontaneously” are normally retained as mastery evidence rather than selected for deliberate practice.

For a challenge, V1 chooses up to three in-progress terms. It ranks topic matches first, then terms at retrieval stages (especially Recalled and Spoken), then least recently updated terms, with ID as the deterministic tiebreaker. A challenge can reference vocabulary, but V1 does not make unencountered vocabulary a hidden requirement.
## Practice evidence

When a completed analysis deterministically finds an exact challenge-owned
target word or phrase in the normalized transcript, Oratry creates one
immutable `vocabulary_observations` row for that run and links it to the
learner's Word Bank item. This is evidence of target occurrence, not a claim
that the word was used appropriately. The Vocabulary surface shows the count
and last observed date.

Deleting a Word Bank item only removes that learner-facing item: the
observation remains linked to the user and analysis run, while its optional
item reference becomes null. Dictionary cache data and LLM interpretation
never create vocabulary observations.
