export type Skill = "Thinking" | "Structure" | "Clarity" | "Language" | "Fluency" | "Delivery";
export type Challenge = { id: string; title: string; prompt: string; difficulty: "Foundation" | "Stretch"; duration: number; targetSkills: Skill[]; guidance: string[] };
export type Metric = { label: string; value: string; note: string };
export type Result = { overall: number; scores: Record<Skill, number>; metrics: Metric[]; transcript: string; focus: { skill: Skill; observation: string; action: string; criterion: string } };
