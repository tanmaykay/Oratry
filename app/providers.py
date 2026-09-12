"""Replaceable, provider-neutral ports and local development adapters."""
from dataclasses import dataclass
from typing import Protocol
@dataclass
class Transcript: text:str; segments:list[dict]; language:str; confidence:float; provider:str; model:str
@dataclass
class RubricEvaluation: dimensions:dict[str,int]; observations:list[dict]; evidence:list[dict]; provider:str; model:str
class TranscriptionPort(Protocol):
    def transcribe(self, object_key:str, language_hint:str|None=None)->Transcript: ...
class EvaluationPort(Protocol):
    def evaluate(self, transcript:Transcript, challenge_prompt:str, metrics:dict)->RubricEvaluation: ...
class DemoTranscriber:
    def transcribe(self, object_key, language_hint=None): return Transcript("This is a local development transcript for the submitted speaking attempt.",[{"startMs":0,"endMs":5000,"text":"This is a local development transcript for the submitted speaking attempt."}],language_hint or "en",.8,"demo","demo-stt-1")
class RulesEvaluator:
    def evaluate(self, transcript, challenge_prompt, metrics):
        fluency=max(0,min(100,round(80-metrics["fillerCount"]*5)))
        return RubricEvaluation({"structure":70,"clarity":72,"fluency":fluency,"language":68,"delivery":70},[{"dimension":"structure","observation":"The response has a discernible central point."}],[],"rules","rules-evaluator-1")
