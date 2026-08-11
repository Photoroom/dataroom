import React, { useEffect, useMemo, useState } from "react";
import { twMerge } from "tailwind-merge";
import { useSearchParams } from "react-router-dom";
import { CheckIcon, LockClosedIcon, MagnifyingGlassIcon } from "@heroicons/react/20/solid";
import { useDatasetsList, useGroupTypesList } from "../../api/client";
import { Dataset } from "../../api/client.schemas";
import { formatNumber } from "../../utils/formatNumber";
import { PICKER_PAGE_SIZE } from "./constants";

// Single-type dropdown + always-on multi-dataset picker + thumbnail-role
// chips. One type at a time keeps every visible group selectable together
// (selection is locked to a single type), and once a type is chosen its
// declared roles are known — the chips switch which member image each card
// uses as its thumbnail (?cover_role=). Datasets hold a single type, so an
// active dataset selection LOCKS the type dropdown to it and datasets of a
// different type can't be mixed into the selection.
export const GroupsFilterSidebar: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [datasetQuery, setDatasetQuery] = useState("");

  // Old links may carry a CSV (?type=a,b) from the multi-select era — use the first.
  const selectedType = (searchParams.get("type") ?? "").split(",").filter(Boolean)[0] ?? "";
  const coverRole = searchParams.get("cover_role") ?? "";
  // CSV, any-of: groups that are members of at least one listed dataset
  const selectedDatasets = (searchParams.get("dataset") ?? "").split(",").filter(Boolean);

  // Name filter is a local draft committed to the URL on Enter (a refetch per
  // keystroke would hit the list endpoint on every character). The effect
  // re-syncs the draft when the URL changes elsewhere (Clear / back nav).
  const namePrefix = searchParams.get("name__prefix") ?? "";
  const [namePrefixDraft, setNamePrefixDraft] = useState(namePrefix);
  useEffect(() => setNamePrefixDraft(namePrefix), [namePrefix]);

  const commitNamePrefix = () => {
    const next = new URLSearchParams(searchParams);
    if (namePrefixDraft) next.set("name__prefix", namePrefixDraft);
    else next.delete("name__prefix");
    setSearchParams(next);
  };

  // Whole type catalogue in one request — the dropdown lists them all.
  const { data: groupTypes, isLoading } = useGroupTypesList({ page_size: PICKER_PAGE_SIZE });
  const allTypes = useMemo(() => groupTypes?.results ?? [], [groupTypes]);
  const selectedTypeObj = useMemo(() => allTypes.find(t => t.name === selectedType), [allTypes, selectedType]);
  const availableRoles = selectedTypeObj?.roles ?? [];

  // Dataset catalogue, filtered in-memory as you type. It follows the selected
  // type: the picker only offers datasets whose groups this view can show.
  const { data: datasetsData, isLoading: isLoadingDatasets } = useDatasetsList({
    page_size: PICKER_PAGE_SIZE,
    type: selectedType || undefined,
  });
  // biggest datasets first — the list endpoint has no ordering param
  const allDatasets = useMemo(
    () => [...(datasetsData?.results ?? [])].sort((a, b) => b.group_count - a.group_count),
    [datasetsData]
  );
  const datasets = useMemo(() => {
    const q = datasetQuery.trim().toLowerCase();
    return q
      ? allDatasets.filter(d => d.name.toLowerCase().includes(q) || d.slug_version.toLowerCase().includes(q))
      : allDatasets;
  }, [allDatasets, datasetQuery]);

  // A dataset selection implies its type — the dropdown is locked to it.
  const lockedType = selectedDatasets.length
    ? (allDatasets.find(d => selectedDatasets.includes(d.slug_version))?.type ?? selectedType)
    : "";

  const setType = (name: string) => {
    const next = new URLSearchParams(searchParams);
    if (name) next.set("type", name);
    else next.delete("type");
    // A thumbnail role only means something for the type that declares it.
    const declares = allTypes.find(t => t.name === name)?.roles?.some(r => r.role === coverRole);
    if (!declares) next.delete("cover_role");
    // Leftover from the removed multi-select role filter.
    next.delete("roles");
    setSearchParams(next);
  };

  const toggleDataset = (d: Dataset) => {
    const next = new URLSearchParams(searchParams);
    const list = selectedDatasets.includes(d.slug_version)
      ? selectedDatasets.filter(s => s !== d.slug_version)
      : [...selectedDatasets, d.slug_version];
    if (list.length) next.set("dataset", list.join(","));
    else next.delete("dataset");
    if (list.length) {
      // The selection holds one type (mixing is prevented below), so lock the
      // type filter to it; keeps role chips and Select mode working.
      next.set("type", d.type);
      const declares = allTypes.find(t => t.name === d.type)?.roles?.some(r => r.role === coverRole);
      if (!declares) next.delete("cover_role");
    }
    next.delete("roles");
    setSearchParams(next);
  };

  const setCoverRole = (role: string) => {
    const next = new URLSearchParams(searchParams);
    if (role) next.set("cover_role", role);
    else next.delete("cover_role");
    setSearchParams(next);
  };

  const anyActive = Boolean(selectedType || coverRole || namePrefix || selectedDatasets.length);

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
              for (const p of ["type", "cover_role", "name__prefix", "roles", "dataset"]) {
                next.delete(p);
              }
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
          <div className="text-[10px] uppercase tracking-wide opacity-50 mb-1">Name prefix</div>
          <form
            onSubmit={e => {
              e.preventDefault();
              commitNamePrefix();
            }}
            className="relative"
          >
            <MagnifyingGlassIcon className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 opacity-40" />
            <input
              type="text"
              value={namePrefixDraft}
              onChange={e => setNamePrefixDraft(e.target.value)}
              placeholder="e.g. zara_  ↵"
              className="w-full text-xs pl-7 pr-2 py-1.5 rounded bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30"
            />
          </form>
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1 text-[10px] uppercase tracking-wide opacity-50">
            Type
            {lockedType && <LockClosedIcon className="size-3" />}
          </div>
          <select
            value={selectedType}
            disabled={Boolean(lockedType) || isLoading}
            onChange={e => setType(e.target.value)}
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
          {lockedType && <div className="text-[10px] opacity-50">locked by the dataset filter</div>}
          {Boolean(groupTypes?.next) && (
            <div className="text-[10px] text-amber-600 dark:text-amber-400">
              Showing only the first {PICKER_PAGE_SIZE} types.
            </div>
          )}
        </div>

        {selectedTypeObj && availableRoles.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <div className="text-[10px] uppercase tracking-wide opacity-50">Thumbnail</div>
            <div className="flex flex-wrap gap-1">
              <button
                type="button"
                onClick={() => setCoverRole("")}
                title="The group's default cover: its explicit cover image, else the first image added"
                className={twMerge(
                  "text-xs px-2 py-0.5 rounded-full border transition-colors cursor-pointer",
                  coverRole === ""
                    ? "bg-brand-400/20 border-brand-400/40 text-brand-500 dark:text-brand-400 font-medium"
                    : "border-black/10 dark:border-white/10 opacity-60 hover:opacity-100"
                )}
              >
                cover
              </button>
              {availableRoles.map(r => (
                <button
                  key={r.role}
                  type="button"
                  onClick={() => setCoverRole(r.role)}
                  title={r.is_required ? `${r.role} (required role)` : r.role}
                  className={twMerge(
                    "text-xs px-2 py-0.5 rounded-full border transition-colors cursor-pointer",
                    coverRole === r.role
                      ? "bg-brand-400/20 border-brand-400/40 text-brand-500 dark:text-brand-400 font-medium"
                      : "border-black/10 dark:border-white/10 opacity-60 hover:opacity-100"
                  )}
                >
                  {r.role}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <div className="text-[10px] uppercase tracking-wide opacity-50">Datasets</div>
          <div className="relative">
            <MagnifyingGlassIcon className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 opacity-40" />
            <input
              type="text"
              value={datasetQuery}
              onChange={e => setDatasetQuery(e.target.value)}
              placeholder="Filter datasets…"
              className="w-full text-xs pl-7 pr-2 py-1.5 rounded bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30"
            />
          </div>
          <div className="flex flex-col gap-0.5 max-h-60 overflow-y-auto">
            {isLoadingDatasets && <div className="text-xs opacity-50 px-2 py-1">Loading…</div>}
            {!isLoadingDatasets && datasets.length === 0 && (
              <div className="text-xs opacity-50 px-2 py-1">No datasets match.</div>
            )}
            {!isLoadingDatasets &&
              datasets.map(d => {
                const active = selectedDatasets.includes(d.slug_version);
                // The selection holds one type — other-type datasets can't join it.
                const disabled = !active && Boolean(lockedType) && d.type !== lockedType;
                return (
                  <button
                    key={d.slug_version}
                    type="button"
                    disabled={disabled}
                    onClick={() => toggleDataset(d)}
                    title={disabled ? `Different type (${d.type})` : `${d.slug_version} · ${d.type}`}
                    className={twMerge(
                      "flex items-center gap-2 w-full text-left text-sm px-2 py-1 rounded transition-colors cursor-pointer",
                      active ? "bg-black/10 dark:bg-white/10 font-medium" : "hover:bg-black/5 dark:hover:bg-white/5",
                      disabled && "opacity-40 cursor-not-allowed hover:bg-transparent dark:hover:bg-transparent"
                    )}
                  >
                    <span className="size-3 shrink-0">{active && <CheckIcon className="size-3" />}</span>
                    <span className="truncate flex-1">
                      {d.name} <span className="opacity-40">v{d.version}</span>
                    </span>
                    <span className="shrink-0 text-[10px] tabular-nums opacity-40">
                      {formatNumber(d.group_count, { decimals: 0 })}
                    </span>
                  </button>
                );
              })}
          </div>
          {Boolean(datasetsData?.next) && (
            <div className="text-[10px] text-amber-600 dark:text-amber-400">
              Showing first {PICKER_PAGE_SIZE} datasets — narrow the search to find more.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
