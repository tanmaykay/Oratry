# Personalization

V1 personalization is deterministic (`rules-1`), explainable, and based only on recorded evidence. It does not use ML or infer ability when analysis is absent.

For every core skill—Thinking, Structure, Language, Fluency, and Delivery—the system appends an observation from a completed analysis. The current state is a projection of at most five most-recent observations, weighted by their recorded confidence. The projection records its model version, confidence, and latest evidence time. An empty or zero-confidence input leaves the existing state untouched.

The next assignment is selected from the approved curriculum. Its explanation identifies the need, goal relevance, difficulty fit, novelty, vocabulary relevance, and recency factors that affected its rank. No arbitrary free-text prompt is an eligible challenge.

# Recommendation order

1. Skill need (40%): weaker target skills are preferred.
2. Goal relevance (20%): exact topic, then keyword overlap, then neutral relevance.
3. Appropriate difficulty (18%): distance over all seven difficulty dimensions, including the learner's topic familiarity.
4. Variety (12%): avoid a repeated challenge or family during the prior 14 days.
5. Vocabulary relevance (5%): include in-progress vocabulary where appropriate.
6. Recency (5%): avoid overusing the same cognitive task in the last three challenges.

Ties resolve by stable challenge ID, so identical inputs always produce the same assignment.
