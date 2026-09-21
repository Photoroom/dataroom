/** Below this many held-out examples on a side, the metrics a training reports
 * move by a lot per image: average precision on one or two positives says more
 * about which images the draw took than about the model.
 *
 * Deliberately not a limit anywhere. A classifier with eight positives should
 * still be trainable — you cannot label your way up to a measurable set without
 * training and looking at scores on the way — so this only decides when the app
 * says the numbers cannot be trusted yet.
 */
export const MEASURABLE_PER_SIDE = 3;

/** What share of a version's examples are held out, as whole percent. */
export const heldOutShare = (counts: { pos: number; neg: number; val_pos: number; val_neg: number }): number => {
  const examples = counts.pos + counts.neg;
  return examples ? Math.round(((counts.val_pos + counts.val_neg) / examples) * 100) : 0;
};
