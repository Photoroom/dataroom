import { ClassifierApplyRun } from "../../api/client.schemas";

export const isRunActive = (run: ClassifierApplyRun) => run.status === "launched" || run.status === "running";

/** Poll the runs list every 2s while any run is still going. */
export const pollWhileRunning = (query: { state: { data?: ClassifierApplyRun[] } }) =>
  (query.state.data ?? []).some(isRunActive) ? 2000 : false;
