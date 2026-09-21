import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { OSImage } from "../api/client.schemas";

/** Which side of a classifier an image is on, if any. */
export type AnnotatedSide = "positive" | "negative" | null;

/** What a click has staged for an image. ``clear`` is the way back out: it
 * takes a saved annotation off both sides, so it only exists for images that have
 * a saved side to lose. */
export type StagedMark = "positive" | "negative" | "clear";

export type StagedLabels = Record<StagedMark, string[]>;

interface ClassifierAnnotationValue {
  /** The side an image is already saved as. */
  sideOf: (image: OSImage) => AnnotatedSide;
  /** What an image is staged as, not yet saved. */
  stagedSide: (imageId: string) => StagedMark | null;
  /** Cycle a click: unlabelled, positive, negative, unlabelled. */
  cycle: (imageId: string) => void;
  /** Stage one specific mark, whatever the image carries now; null unstages.
   * ``clear`` has no place in the click cycle — removing an annotation is a
   * deliberate act, reached by its own button rather than by clicking past the
   * two labels. */
  setMark: (imageId: string, mark: StagedMark | null) => void;
  staged: StagedLabels;
  clearStaged: () => void;
  markLocally: (imageIds: string[], side: AnnotatedSide) => void;
  isAnnotating: boolean;
}

const NOTHING_STAGED: StagedLabels = { positive: [], negative: [], clear: [] };
const MARKS: StagedMark[] = ["positive", "negative", "clear"];

const stagedMarkOf = (staged: StagedLabels, imageId: string) => MARKS.find(mark => staged[mark].includes(imageId));

// Outside the annotate workspace nothing is marked or staged, so the plain
// image browser pays one context read and behaves exactly as before.
const ClassifierAnnotationContext = createContext<ClassifierAnnotationValue>({
  sideOf: () => null,
  stagedSide: () => null,
  cycle: () => {},
  setMark: () => {},
  staged: NOTHING_STAGED,
  clearStaged: () => {},
  markLocally: () => {},
  isAnnotating: false,
});

export const useClassifierAnnotation = () => useContext(ClassifierAnnotationContext);

/** Labelling state for the annotate workspace.
 *
 * Membership is read straight off each image's ``datasets`` denorm, which the
 * image list already returns, so no extra request. Clicks stage a side rather
 * than writing immediately, so a mis-click costs nothing and a whole screen of
 * decisions commits in one batch.
 */
export const ClassifierAnnotationProvider: React.FC<{
  posDatasets: string[];
  negDatasets: string[];
  isAnnotating?: boolean;
  children: React.ReactNode;
}> = ({ posDatasets, negDatasets, isAnnotating = false, children }) => {
  // Adding an image to a dataset updates its `datasets` denorm through an async
  // update_by_query, so it is not in the next list response yet. These
  // overrides badge what was just saved; the denorm catches up and agrees.
  const [justLabelled, setJustLabelled] = useState<Record<string, AnnotatedSide>>({});
  const [staged, setStaged] = useState<StagedLabels>(NOTHING_STAGED);

  const markLocally = useCallback((imageIds: string[], side: AnnotatedSide) => {
    setJustLabelled(prev => {
      const next = { ...prev };
      for (const imageId of imageIds) next[imageId] = side;
      return next;
    });
  }, []);

  const clearStaged = useCallback(() => setStaged(NOTHING_STAGED), []);

  const withoutImage = (staged: StagedLabels, imageId: string): StagedLabels => ({
    positive: staged.positive.filter(id => id !== imageId),
    negative: staged.negative.filter(id => id !== imageId),
    clear: staged.clear.filter(id => id !== imageId),
  });

  const setMark = useCallback((imageId: string, mark: StagedMark | null) => {
    setStaged(prev => {
      const without = withoutImage(prev, imageId);
      return mark === null ? without : { ...without, [mark]: [...without[mark], imageId] };
    });
  }, []);

  const cycle = useCallback((imageId: string) => {
    setStaged(prev => {
      const current = stagedMarkOf(prev, imageId);
      const without = withoutImage(prev, imageId);
      const stage = (mark: StagedMark) => ({ ...without, [mark]: [...without[mark], imageId] });
      // One click positive, two negative, three back to unstaged. A staged
      // removal is left alone by the cycle: clicking a tile is how you label,
      // and it should not be able to walk into or out of a removal by accident.
      if (current === undefined) return stage("positive");
      if (current === "positive") return stage("negative");
      return without;
    });
  }, []);

  const value = useMemo(() => {
    const pos = new Set(posDatasets);
    const neg = new Set(negDatasets);
    return {
      isAnnotating,
      staged,
      cycle,
      setMark,
      clearStaged,
      markLocally,
      stagedSide: (imageId: string): StagedMark | null => stagedMarkOf(staged, imageId) ?? null,
      sideOf: (image: OSImage): AnnotatedSide => {
        if (image.id in justLabelled) return justLabelled[image.id];
        const datasets = image.datasets ?? [];
        if (datasets.some(slugVersion => pos.has(slugVersion))) return "positive";
        if (datasets.some(slugVersion => neg.has(slugVersion))) return "negative";
        return null;
      },
    };
  }, [posDatasets, negDatasets, justLabelled, staged, cycle, setMark, clearStaged, markLocally, isAnnotating]);

  return <ClassifierAnnotationContext.Provider value={value}>{children}</ClassifierAnnotationContext.Provider>;
};
