import React, { useEffect, useMemo, useState } from "react";
import { twMerge } from "tailwind-merge";
import { useSearchParams } from "react-router-dom";
import { MagnifyingGlassIcon } from "@heroicons/react/20/solid";
import { useGroupTypesList } from "../../api/client";
import { formatNumber } from "../../utils/formatNumber";
import { PICKER_PAGE_SIZE } from "../groups/constants";

// Datasets list filters, mirroring the groups sidebar idiom: name search
// (committed on Enter), a single-type dropdown, frozen-state chips, and a
// toggle for showing every version instead of only each slug's latest.
export const DatasetsFilterSidebar: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const selectedType = searchParams.get("type") ?? "";
  const frozen = searchParams.get("is_frozen") ?? ""; // "", "true", "false"
  const allVersions = searchParams.get("all_versions") === "1";

  // Search is a local draft committed on Enter (the list endpoint would
  // refetch per keystroke otherwise); re-synced when the URL changes elsewhere.
  const search = searchParams.get("search") ?? "";
  const [searchDraft, setSearchDraft] = useState(search);
  useEffect(() => setSearchDraft(search), [search]);

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  // Types with datasets get the dropdown; counts come from the type catalogue.
  const { data: groupTypes, isLoading } = useGroupTypesList({ page_size: PICKER_PAGE_SIZE });
  const allTypes = useMemo(() => groupTypes?.results ?? [], [groupTypes]);

  const anyActive = Boolean(selectedType || frozen || search || allVersions);

  const frozenOptions = [
    { value: "", label: "all" },
    { value: "false", label: "active" },
    { value: "true", label: "frozen" },
  ];

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
            onClick={() => {
              const next = new URLSearchParams(searchParams);
              for (const p of ["type", "is_frozen", "search", "all_versions"]) next.delete(p);
              setSearchParams(next);
            }}
            className="text-[10px] uppercase opacity-50 hover:opacity-100 cursor-pointer"
          >
            Clear
          </button>
        )}
      </div>

      <div className="px-3 py-2 flex flex-col gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-wide opacity-50 mb-1">Search</div>
          <form
            onSubmit={e => {
              e.preventDefault();
              update("search", searchDraft);
            }}
            className="relative"
          >
            <MagnifyingGlassIcon className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 opacity-40" />
            <input
              type="text"
              value={searchDraft}
              onChange={e => setSearchDraft(e.target.value)}
              placeholder="name or slug  ↵"
              className="w-full text-xs pl-7 pr-2 py-1.5 rounded bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30"
            />
          </form>
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="text-[10px] uppercase tracking-wide opacity-50">Type</div>
          <select
            value={selectedType}
            disabled={isLoading}
            onChange={e => update("type", e.target.value)}
            className="w-full text-xs px-2 py-1.5 rounded bg-black/5 dark:bg-white/5 dark:bg-dark-100 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="">All types</option>
            {selectedType && !allTypes.some(t => t.name === selectedType) && (
              <option value={selectedType}>{selectedType}</option>
            )}
            {allTypes.map(t => (
              <option key={t.name} value={t.name}>
                {t.name} ({formatNumber(t.group_count, { decimals: 0 })})
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="text-[10px] uppercase tracking-wide opacity-50">State</div>
          <div className="flex flex-wrap gap-1">
            {frozenOptions.map(o => (
              <button
                key={o.value}
                type="button"
                onClick={() => update("is_frozen", o.value)}
                className={twMerge(
                  "text-xs px-2 py-0.5 rounded-full border transition-colors cursor-pointer",
                  frozen === o.value
                    ? "bg-brand-400/20 border-brand-400/40 text-brand-500 dark:text-brand-400 font-medium"
                    : "border-black/10 dark:border-white/10 opacity-60 hover:opacity-100"
                )}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
          <input
            type="checkbox"
            checked={allVersions}
            onChange={e => update("all_versions", e.target.checked ? "1" : "")}
            className="size-3.5 accent-brand-400 cursor-pointer"
          />
          <span className="opacity-70">Show all versions</span>
        </label>
      </div>
    </div>
  );
};
