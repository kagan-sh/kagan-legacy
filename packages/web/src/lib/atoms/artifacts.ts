import { atom } from 'jotai';

// ---------------------------------------------------------------------------
// Artifact types
// ---------------------------------------------------------------------------

export type ArtifactType = 'html' | 'svg' | 'markdown';

export interface Artifact {
  id: string;
  type: ArtifactType;
  content: string;
  title?: string;
}

// ---------------------------------------------------------------------------
// Atom
// ---------------------------------------------------------------------------

export const artifactsAtom = atom<Artifact[]>([]);

export const addArtifactAtom = atom(
  null,
  (_get, set, artifact: Omit<Artifact, 'id'>) => {
    const id = `artifact-${crypto.randomUUID()}`;
    set(artifactsAtom, (prev) => [...prev, { ...artifact, id }]);
  },
);

export const clearArtifactsAtom = atom(null, (_get, set) => {
  set(artifactsAtom, []);
});
