import type { FilmCredits } from './FilmCredits';

export type FilmConcept = {
  premise: string;
  protagonist: string;
  motivation: string;
  relationships: string;
  beginning: string;
  conflict: string;
  turningPoint: string;
  resolution: string;
  visualMotif: string;
  continuityRules: string;
};

export type CreativeControls = {
  visualStyle: string; setting: string; cast: string; mood: string;
  ending: string; camera: string; mustInclude: string; avoid: string;
};

export type FilmSetupPayload = {
  title: string; artist: string; direction: string;
  treatment: 'story' | 'mixed' | 'performance';
  creative: CreativeControls; concept: FilmConcept | null;
  sceneSeconds: number; sceneTiming: 'storyboard' | 'beats' | 'fixed';
  renderTier: 'standard' | 'native'; credits: FilmCredits;
  workflow: 'short-film';
};

export const emptyCreative: CreativeControls = {
  visualStyle:'',setting:'',cast:'',mood:'',ending:'',camera:'',mustInclude:'',avoid:'',
};
export const emptyConcept: FilmConcept = {
  premise:'',protagonist:'',motivation:'',relationships:'',beginning:'',conflict:'',turningPoint:'',resolution:'',visualMotif:'',continuityRules:'',
};
export const conceptMinimums: Record<keyof FilmConcept,number> = {
  premise:20,protagonist:5,motivation:10,relationships:10,beginning:20,conflict:20,turningPoint:20,resolution:20,visualMotif:10,continuityRules:10,
};
export const completeConcept = (concept: FilmConcept | null) => !!concept &&
  Object.entries(conceptMinimums).every(([key,n]) => concept[key as keyof FilmConcept].trim().length >= n);

export type StoryScene = {
  name: string; endSeconds: number;
  beat: 'beginning' | 'conflict' | 'turning-point' | 'resolution' | 'performance';
  purpose: string; cause: string; characterReason: string; action: string;
  framing: string; locationId: string; startState: string; endState: string; continuity: string;
  castIds: string[]; vocalistId: string | null;
};
