import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { twMerge } from "tailwind-merge";
import { CheckIcon, MagnifyingGlassIcon } from "@heroicons/react/20/solid";

/** What the classifier list is actually narrowed by.
 *
 * Two things, because there are only two worth having: which versions to show,
 * and a name prefix. Faceting by lock state or embedding space sounded useful
 * and was not — a classifier list is short, and you find one by name.
 */
const RadioRow: React.FC<{ label: string; isActive: boolean; onSelect: () => void }> = ({
  label,
  isActive,
  onSelect,
}) => (
  <button
    type="button"
    onClick={onSelect}
    className={twMerge(
      "flex items-center gap-2 w-full text-left text-sm px-2 py-1 rounded transition-colors cursor-pointer",
      isActive ? "bg-black/10 dark:bg-white/10 font-medium" : "hover:bg-black/5 dark:hover:bg-white/5"
    )}
  >
    <span className="size-3 shrink-0">{isActive && <CheckIcon className="size-3" />}</span>
    <span className="truncate flex-1">{label}</span>
  </button>
);

export const ClassifiersFilterSidebar: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const showAllVersions = searchParams.get("all_versions") === "1";

  // Local draft committed on Enter: a refetch per keystroke would hit the list
  // endpoint on every character. The effect re-syncs when the URL changes
  // elsewhere (Clear, back nav).
  const namePrefix = searchParams.get("name__prefix") ?? "";
  const [namePrefixDraft, setNamePrefixDraft] = useState(namePrefix);
  useEffect(() => setNamePrefixDraft(namePrefix), [namePrefix]);

  const setParams = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(searchParams);
    mutate(next);
    // The peeked classifier belongs to the previous result set.
    next.delete("peek");
    setSearchParams(next);
  };

  const anyActive = Boolean(showAllVersions || namePrefix);

  return (
    <div
      className={twMerge(
        "fixed left-0 bottom-0 z-20",
        "sm:top-14 top-[5.5rem]",
        "w-60 bg-light-100 dark:bg-dark-100",
        "border-r border-light-300 dark:border-dark-300",
        "overflow-y-auto flex flex-col",
        "hidden sm:flex"
      )}
    >
      <div className="sticky top-0 z-10 bg-light-100 dark:bg-dark-100 px-3 py-2 flex items-center justify-between border-b border-light-300 dark:border-dark-300">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-black/40 dark:text-white/40">
          Filters
        </span>
        {anyActive && (
          <button
            type="button"
            onClick={() => setParams(next => ["all_versions", "name__prefix"].forEach(p => next.delete(p)))}
            className="text-[10px] uppercase opacity-50 hover:opacity-100 cursor-pointer"
          >
            Clear
          </button>
        )}
      </div>

      <div className="px-3 py-2 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <div className="text-[10px] uppercase tracking-wide opacity-50">Name prefix</div>
          <form
            onSubmit={e => {
              e.preventDefault();
              setParams(next => {
                if (namePrefixDraft) next.set("name__prefix", namePrefixDraft);
                else next.delete("name__prefix");
              });
            }}
            className="relative"
          >
            <MagnifyingGlassIcon className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 opacity-40" />
            <input
              type="text"
              value={namePrefixDraft}
              onChange={e => setNamePrefixDraft(e.target.value)}
              placeholder="e.g. studio  ↵"
              className="w-full text-xs pl-7 pr-2 py-1.5 rounded bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30"
            />
          </form>
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="text-[10px] uppercase tracking-wide opacity-50">Versions</div>
          <div className="flex flex-col gap-0.5">
            <RadioRow
              label="Latest only"
              isActive={!showAllVersions}
              onSelect={() => setParams(next => next.delete("all_versions"))}
            />
            <RadioRow
              label="All versions"
              isActive={showAllVersions}
              onSelect={() => setParams(next => next.set("all_versions", "1"))}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
