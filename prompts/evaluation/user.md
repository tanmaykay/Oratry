# Evaluation input template

Render this template as JSON in the user message. Omit no required input field; represent unavailable metrics explicitly as unavailable before this stage, rather than as zero.

```json
{
  "challenge": "{{challenge}}",
  "prompt": "{{prompt}}",
  "target_skill": "{{target_skill}}",
  "transcript": "{{transcript}}",
  "speech_metrics": {{speech_metrics_json}},
  "target_vocabulary": {{target_vocabulary_json}},
  "previous_performance": {{previous_performance_json}},
  "user_skill_profile": {{user_skill_profile_json}}
}
```

`previous_performance` and `user_skill_profile` are optional calibration context only. They cannot create evidence about this attempt or override its transcript/metrics.
