# Challenge engine

The engine selects, rather than randomly generates, an active curriculum challenge. Inputs are user goals, skill deficits, recent challenge history, desired difficulty, topic familiarity, cognitive task, target skill, and vocabulary history.

Supported cognitive tasks are Explain, Argue, Oppose, Compare, Persuade, Synthesize, Story, and Impromptu.

Difficulty is a vector, not a scalar: topic familiarity, cognitive complexity, preparation time, speaking time, vocabulary difficulty, opposition, and pressure are individually scored from 1 to 5. A displayed overall level may be the rounded average, but selection uses the individual dimensions.

Before a challenge can be assigned it must be active and have an ID, non-empty prompt, preparation guidance, topic, valid core target skills, and 15–1800 seconds of speaking time. High speaking-time difficulty requires at least 90 seconds; an Oppose task requires opposition of at least 2. Invalid candidates are discarded and an empty valid set fails explicitly.

The engine returns the chosen challenge and human-readable reasons. It never supplies arguments, evidence, or a response for the learner.
