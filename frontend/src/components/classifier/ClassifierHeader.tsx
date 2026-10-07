import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import ReactDOM from "react-dom";
import toast from "react-hot-toast";
import { twMerge } from "tailwind-merge";
import { LockClosedIcon, LockOpenIcon, PencilSquareIcon, PlusIcon } from "@heroicons/react/24/outline";
import { useQueryClient } from "@tanstack/react-query";
import {
  useClassifiersLockCreate,
  useClassifiersUnlockCreate,
  useClassifiersNewVersionCreate,
  useClassifiersPartialUpdate,
  useClassifiersList,
  getClassifiersListQueryKey,
} from "../../api/client";
import { Classifier } from "../../api/client.schemas";
import { extractApiError } from "../../api/errors";
import { formatNumber } from "../../utils/formatNumber";
import { HowClassifiersWork } from "./HowClassifiersWork";
import Popup from "../common/Popup";
import { URLS } from "../../urls";

// newest N version chips shown before the "+N more" toggle, as on a dataset
const MAX_VERSION_CHIPS = 6;

/** One side's borrowed datasets, each with its own tickbox. Carrying them over
 * is a per-dataset choice: a new version often exists precisely to stop
 * training on one of them. */
const ExtraDatasetChecklist: React.FC<{
  side: "positive" | "negative";
  datasets: string[];
  isKept: (slugVersion: string) => boolean;
  onToggle: (slugVersion: string) => void;
}> = ({ side, datasets, isKept, onToggle }) => {
  if (datasets.length === 0) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <span
        className={twMerge(
          "text-[11px] font-medium capitalize",
          side === "positive" ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"
        )}
      >
        {side}
      </span>
      {datasets.map(slugVersion => (
        <label key={slugVersion} className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="cursor-pointer"
            checked={isKept(slugVersion)}
            onChange={() => onToggle(slugVersion)}
          />
          <span className="font-mono text-xs truncate">{slugVersion}</span>
        </label>
      ))}
    </div>
  );
};

/** This version's note, read and written in place.
 *
 * A note is worth little if writing it costs a dialog, so it edits where it is
 * read: click it, type, save. An empty one leaves a quiet prompt rather than
 * nothing, otherwise the field would only ever be filled at branch time.
 */
const VersionNote: React.FC<{ classifier: Classifier; onChanged: () => void }> = ({ classifier, onChanged }) => {
  const queryClient = useQueryClient();
  const { mutateAsync: updateClassifier } = useClassifiersPartialUpdate();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(classifier.version_note ?? "");
  const [isSaving, setIsSaving] = useState(false);

  const startEditing = () => {
    setDraft(classifier.version_note ?? "");
    setIsEditing(true);
  };

  const save = async () => {
    setIsSaving(true);
    try {
      await updateClassifier({ slugVersion: classifier.slug_version, data: { version_note: draft.trim() } });
      setIsEditing(false);
      onChanged();
      // The chips carry the note as their tooltip, and the list page shows it
      // on every card.
      queryClient.invalidateQueries({ queryKey: getClassifiersListQueryKey() });
    } catch (e) {
      toast.error(extractApiError(e, "Error saving the note"));
    } finally {
      setIsSaving(false);
    }
  };

  if (isEditing) {
    return (
      <div className="flex flex-col gap-1.5 border-l-2 border-brand-400 pl-3">
        <textarea
          value={draft}
          onChange={e => setDraft(e.target.value)}
          rows={2}
          autoFocus
          placeholder={`What is v${classifier.version} for?`}
          className="text-sm px-2 py-1.5 rounded bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30 resize-y"
        />
        <div className="flex gap-2">
          <button type="button" className="btn btn-sm btn-primary" onClick={save} disabled={isSaving}>
            {isSaving ? "Saving..." : "Save note"}
          </button>
          <button
            type="button"
            className="btn btn-sm btn-outline"
            onClick={() => setIsEditing(false)}
            disabled={isSaving}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={startEditing}
      title="Edit this version's note"
      className="group text-sm text-left border-l-2 border-black/10 dark:border-white/10 pl-3 cursor-pointer"
    >
      <span className="opacity-50 tabular-nums">v{classifier.version}: </span>
      {classifier.version_note ? (
        <span className="opacity-80">{classifier.version_note}</span>
      ) : (
        <span className="opacity-40 italic">add a note for this version</span>
      )}
      <PencilSquareIcon className="inline w-3.5 h-3.5 ml-1.5 mb-0.5 opacity-0 group-hover:opacity-50 transition-opacity" />
    </button>
  );
};

/** Name, version, lock state, and the two actions that change any of them.
 *
 * Both actions confirm first, spelling out what they do: locking and branching
 * change what a version means, and neither should be discoverable only after
 * the fact through a toast.
 */
export const ClassifierHeader: React.FC<{
  classifier: Classifier;
  onChanged: () => void;
}> = ({ classifier, onChanged }) => {
  const [isBusy, setIsBusy] = useState(false);
  const navigate = useNavigate();
  const { search } = useLocation();
  const queryClient = useQueryClient();
  const { data: versionList } = useClassifiersList({ slug: classifier.slug });
  const { mutateAsync: lock } = useClassifiersLockCreate();
  const { mutateAsync: unlock } = useClassifiersUnlockCreate();
  const { mutateAsync: newVersion } = useClassifiersNewVersionCreate();
  const [confirming, setConfirming] = useState<"lock" | "new-version" | null>(null);
  const [copyAnnotations, setCopyAnnotations] = useState(true);
  const [versionNote, setVersionNote] = useState("");
  // Which borrowed datasets follow into the new version. Null means "not
  // touched yet", so opening the dialog ticks everything the source has.
  const [keptExtras, setKeptExtras] = useState<Set<string> | null>(null);
  const [showAllVersions, setShowAllVersions] = useState(false);

  // Newest first, so the chips read the way a version history does.
  const versions = [...(versionList?.results ?? [])].sort((a, b) => b.version - a.version);
  const isLocked = classifier.is_frozen;
  const extraPos = classifier.extra_pos_datasets ?? [];
  const extraNeg = classifier.extra_neg_datasets ?? [];
  const hasExtras = extraPos.length + extraNeg.length > 0;

  const openNewVersion = () => {
    setVersionNote("");
    setKeptExtras(new Set([...extraPos, ...extraNeg]));
    setConfirming("new-version");
  };

  const isKept = (slugVersion: string) => keptExtras?.has(slugVersion) ?? true;
  const toggleExtra = (slugVersion: string) =>
    setKeptExtras(current => {
      const next = new Set(current ?? [...extraPos, ...extraNeg]);
      if (next.has(slugVersion)) next.delete(slugVersion);
      else next.add(slugVersion);
      return next;
    });

  const doLock = async () => {
    setConfirming(null);
    setIsBusy(true);
    try {
      if (isLocked) await unlock({ slugVersion: classifier.slug_version });
      else await lock({ slugVersion: classifier.slug_version });
      onChanged();
      // onChanged refetches this version only. The version chips come from the
      // list query, so without this the lock a chip shows stays stale.
      queryClient.invalidateQueries({ queryKey: getClassifiersListQueryKey() });
    } catch (e) {
      toast.error(extractApiError(e, "Error changing the lock"));
    } finally {
      setIsBusy(false);
    }
  };

  const doNewVersion = async () => {
    setConfirming(null);
    setIsBusy(true);
    try {
      const created = await newVersion({
        slugVersion: classifier.slug_version,
        data: {
          copy_examples: copyAnnotations,
          version_note: versionNote.trim(),
          extra_pos_datasets: extraPos.filter(isKept),
          extra_neg_datasets: extraNeg.filter(isKept),
        },
      });
      toast.success(`v${created.version} created from v${classifier.version}. You are now editing v${created.version}`);
      // The new version has to appear in the chip row it is about to land on.
      queryClient.invalidateQueries({ queryKey: getClassifiersListQueryKey() });
      navigate(URLS.CLASSIFIER_DETAIL(created.slug, created.version) + search);
    } catch (e) {
      toast.error(extractApiError(e, "Error creating the next version"));
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3 flex-wrap">
        <h5 className="font-bold">{classifier.name}</h5>
        <HowClassifiersWork />
        {versions.length === 1 && <span className="text-xs opacity-50 tabular-nums">v{classifier.version}</span>}

        <div className="flex-1" />

        {isLocked ? (
          <button type="button" className="btn btn-sm btn-primary" onClick={openNewVersion} disabled={isBusy}>
            <PlusIcon className="w-4 h-4" />
            New version
          </button>
        ) : (
          <Link className="btn btn-sm btn-primary" to={URLS.CLASSIFIER_ANNOTATE(classifier.slug, classifier.version)}>
            <PencilSquareIcon className="w-4 h-4" />
            Annotate
          </Link>
        )}
        <button
          type="button"
          className="btn btn-sm btn-outline"
          onClick={() => (isLocked ? doLock() : setConfirming("lock"))}
          disabled={isBusy}
        >
          {isLocked ? <LockOpenIcon className="w-4 h-4" /> : <LockClosedIcon className="w-4 h-4" />}
          {isLocked ? "Unlock" : "Lock"}
        </button>
      </div>

      {/* Versions — the same chip row a dataset uses, for the same reason: the
          versions of a thing are a set you compare, not a list you pick one
          from, and a dropdown hides the sizes and the locks that decide which
          one you want. */}
      {versions.length > 1 && (
        <div className="flex items-center gap-1.5 flex-wrap text-sm">
          <span className="text-xs opacity-50">Versions:</span>
          {(showAllVersions ? versions : versions.slice(0, MAX_VERSION_CHIPS)).map(version => {
            const isCurrent = version.slug_version === classifier.slug_version;
            const total = version.counts.pos + version.counts.neg;
            return (
              <Link
                key={version.slug_version}
                to={URLS.CLASSIFIER_DETAIL(version.slug, version.version) + search}
                title={version.version_note || `${total} annotations`}
                className={twMerge(
                  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs transition-colors",
                  isCurrent
                    ? "bg-brand-100 text-brand-700 font-bold dark:bg-brand-900 dark:text-brand-200"
                    : "bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/20"
                )}
              >
                <span>v{version.version}</span>
                <span className="text-[9px] leading-none px-1 py-0.5 rounded-full bg-black/10 dark:bg-white/25 tabular-nums font-normal">
                  {formatNumber(total, { decimals: 0 })}
                </span>
                {version.is_frozen && <span aria-label="locked">🔒</span>}
              </Link>
            );
          })}
          {versions.length > MAX_VERSION_CHIPS && (
            <button
              type="button"
              onClick={() => setShowAllVersions(showing => !showing)}
              className="text-xs opacity-60 hover:opacity-100 hover:underline cursor-pointer"
            >
              {showAllVersions ? "show less" : `+${versions.length - MAX_VERSION_CHIPS} more`}
            </button>
          )}
        </div>
      )}

      {classifier.description && <p className="text-sm opacity-60">{classifier.description}</p>}

      {/* The classifier's description says what it is; this says what THIS
          version is, which is the thing you need when picking between them.
          Editable even when locked: what a version was for is often only clear
          once it is finished and something newer exists. */}
      <VersionNote classifier={classifier} onChanged={onChanged} />

      {/* A locked version behaves differently enough to say so on the page,
          rather than leaving it to a chip and a changed button. */}
      {isLocked && (
        <div className="flex items-center gap-2 text-xs rounded-lg bg-black/5 dark:bg-white/5 px-3 py-2">
          <LockClosedIcon className="w-4 h-4 shrink-0 opacity-60" />
          <span>
            <strong>v{classifier.version} is locked.</strong> Its annotations cannot change, so labelling and editing
            are off. Continue in v{classifier.version + 1}, which starts as a copy of these annotations.
          </span>
        </div>
      )}

      {confirming &&
        ReactDOM.createPortal(
          <Popup onClose={() => setConfirming(null)}>
            {confirming === "lock" ? (
              <>
                <h5 className="mb-4">Lock v{classifier.version}?</h5>
                <ul className="text-sm flex flex-col gap-2 mb-6 list-disc pl-4">
                  <li>
                    Its annotation datasets are frozen: {classifier.counts.main_pos} positive and{" "}
                    {classifier.counts.main_neg} negative images stay exactly as they are.
                  </li>
                  <li>Labelling and editing this version are switched off.</li>
                  <li>
                    To carry on afterwards you create v{classifier.version + 1}, which copies these annotations into a
                    new set you can keep labelling.
                  </li>
                  <li>You can unlock again at any time.</li>
                </ul>
                <div className="flex gap-2">
                  <button type="button" className="btn btn-primary flex-1" onClick={doLock}>
                    Lock v{classifier.version}
                  </button>
                  <button type="button" className="btn btn-outline flex-1" onClick={() => setConfirming(null)}>
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <h5 className="mb-4">Create v{classifier.version + 1}?</h5>

                <div className="flex flex-col gap-2 mb-4">
                  <label className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="radio"
                      className="mt-1 cursor-pointer"
                      checked={copyAnnotations}
                      onChange={() => setCopyAnnotations(true)}
                    />
                    <span className="text-sm">
                      Start from v{classifier.version}&apos;s annotations
                      <span className="block text-xs opacity-60">
                        Copies {classifier.counts.main_pos} positive and {classifier.counts.main_neg} negative images
                        into new datasets you can keep labelling.
                      </span>
                    </span>
                  </label>
                  <label className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="radio"
                      className="mt-1 cursor-pointer"
                      checked={!copyAnnotations}
                      onChange={() => setCopyAnnotations(false)}
                    />
                    <span className="text-sm">
                      Start empty
                      <span className="block text-xs opacity-60">
                        New, empty datasets. For relabelling from scratch while keeping this classifier&apos;s history.
                      </span>
                    </span>
                  </label>
                </div>

                {hasExtras && (
                  <div className="flex flex-col gap-1.5 mb-4">
                    <span className="text-sm">
                      Additional datasets to carry over
                      <span className="block text-xs opacity-60">
                        Referenced, not copied. Untick one to leave it behind — v{classifier.version + 1} then trains
                        without it.
                      </span>
                    </span>
                    <ExtraDatasetChecklist side="positive" datasets={extraPos} isKept={isKept} onToggle={toggleExtra} />
                    <ExtraDatasetChecklist side="negative" datasets={extraNeg} isKept={isKept} onToggle={toggleExtra} />
                  </div>
                )}

                <label className="flex flex-col gap-1 mb-4">
                  <span className="text-sm">
                    Note for v{classifier.version + 1} <span className="opacity-60">(optional)</span>
                    <span className="block text-xs opacity-60">
                      What this version is for. It stays with this version, unlike the description, which every version
                      shares.
                    </span>
                  </span>
                  <textarea
                    value={versionNote}
                    onChange={e => setVersionNote(e.target.value)}
                    rows={2}
                    placeholder="e.g. dropped the stock photos, relabelling the hard negatives"
                    className="text-sm px-2 py-1.5 rounded bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30 resize-y"
                  />
                </label>

                <ul className="text-xs opacity-70 flex flex-col gap-1.5 mb-6 list-disc pl-4">
                  <li>
                    Either way v{classifier.version + 1} gets its own datasets, so labelling it leaves v
                    {classifier.version} untouched.
                  </li>
                  <li>v{classifier.version} stays locked and browsable.</li>
                </ul>
                <div className="flex gap-2">
                  <button type="button" className="btn btn-primary flex-1" onClick={doNewVersion}>
                    Create v{classifier.version + 1}
                  </button>
                  <button type="button" className="btn btn-outline flex-1" onClick={() => setConfirming(null)}>
                    Cancel
                  </button>
                </div>
              </>
            )}
          </Popup>,
          document.body
        )}
    </div>
  );
};
