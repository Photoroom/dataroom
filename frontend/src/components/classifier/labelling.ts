import { DATASET_MEMBER_UPDATE_LIMIT } from "../dataset/AddToDatasetForm";

export const chunk = <T>(items: T[], size: number): T[][] => {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
};

/** Run a dataset write in server-sized batches, reporting progress as it goes.
 *
 * Every dataset write is capped server-side, so labelling N images is
 * ceil(N / 100) requests rather than one rejected call.
 */
export async function inBatches(
  imageIds: string[],
  action: (ids: string[]) => Promise<unknown>,
  report?: (done: number) => void
): Promise<number> {
  let done = 0;
  for (const batch of chunk(imageIds, DATASET_MEMBER_UPDATE_LIMIT)) {
    await action(batch);
    done += batch.length;
    report?.(done);
  }
  return done;
}
