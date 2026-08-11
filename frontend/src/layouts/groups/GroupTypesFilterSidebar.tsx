import React, { useEffect, useMemo, useState } from "react";
import { twMerge } from "tailwind-merge";
import { useSearchParams } from "react-router-dom";
import { CheckIcon, MagnifyingGlassIcon } from "@heroicons/react/20/solid";
import { useRolesList } from "../../api/client";
import { PICKER_PAGE_SIZE } from "./constants";

const PREFIX_PARAM = "name__prefix";
const REQUIRED_ROLES_PARAM = "required_roles";
// plain selection: the type declares the role, required OR optional
const ROLES_PARAM = "roles";
// pre-`roles` picker wrote this; only cleared/considered for legacy URLs
const LEGACY_OPTIONAL_PARAM = "optional_roles";

const readCsv = (params: URLSearchParams, key: string) => (params.get(key) ?? "").split(",").filter(Boolean);

// One picker for both role filters: clicking a role selects it (matching types
// that DECLARE it, required or optional); ticking its "required" column
// checkbox narrows the match to types that REQUIRE it. Maps to the API's
// roles/required_roles params.
const RolePicker: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");

  const required = useMemo(() => readCsv(searchParams, REQUIRED_ROLES_PARAM), [searchParams]);
  const optional = useMemo(() => readCsv(searchParams, ROLES_PARAM), [searchParams]);
  const isSelected = (name: string) => required.includes(name) || optional.includes(name);

  // Fetch the whole role catalogue once (page_size up to API_MAX_PAGE_SIZE)
  // and filter in-memory — avoids the first-page truncation a default page
  // size would cause.
  const { data: rolesData, isLoading } = useRolesList({ page_size: PICKER_PAGE_SIZE });
  const roles = useMemo(() => {
    const all = rolesData?.results ?? [];
    const q = query.trim().toLowerCase();
    return q ? all.filter(r => r.name.toLowerCase().includes(q)) : all;
  }, [rolesData, query]);

  const commit = (nextRequired: string[], nextOptional: string[]) => {
    const params = new URLSearchParams(searchParams);
    if (nextRequired.length === 0) params.delete(REQUIRED_ROLES_PARAM);
    else params.set(REQUIRED_ROLES_PARAM, nextRequired.join(","));
    if (nextOptional.length === 0) params.delete(ROLES_PARAM);
    else params.set(ROLES_PARAM, nextOptional.join(","));
    // any interaction supersedes a legacy optional_roles URL
    params.delete(LEGACY_OPTIONAL_PARAM);
    setSearchParams(params);
  };

  const remove = (name: string) => {
    commit(
      required.filter(r => r !== name),
      optional.filter(r => r !== name)
    );
  };

  // Row click toggles selection (selected roles match as optional by default).
  const toggle = (name: string) => {
    if (isSelected(name)) {
      remove(name);
    } else {
      commit(required, [...optional, name]);
    }
  };

  // The "required" column tick. Ticking an unselected role selects it directly
  // as required; unticking keeps it selected but back to optional.
  const setRequired = (name: string, isRequired: boolean) => {
    if (isRequired) {
      commit(
        [...required, name],
        optional.filter(r => r !== name)
      );
    } else {
      commit(
        required.filter(r => r !== name),
        [...optional.filter(r => r !== name), name]
      );
    }
  };

  const selectedChips = [
    ...required.map(r => ({ name: r, isRequired: true })),
    ...optional.map(r => ({ name: r, isRequired: false })),
  ];

  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[10px] uppercase tracking-wide opacity-50">Roles (all of)</div>
      <div className="relative">
        <MagnifyingGlassIcon className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 opacity-40" />
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search roles…"
          className="w-full text-xs pl-7 pr-2 py-1.5 rounded bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30"
        />
      </div>
      {selectedChips.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selectedChips.map(({ name, isRequired }) => (
            <span
              key={name}
              className={twMerge(
                "flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full",
                isRequired
                  ? "bg-brand-400/20 text-brand-400"
                  : "bg-black/10 text-black/60 dark:bg-white/10 dark:text-white/60"
              )}
            >
              <button
                type="button"
                onClick={() => setRequired(name, !isRequired)}
                title={
                  isRequired
                    ? `Types where ${name} is required — click to match any declaration`
                    : `Types that declare ${name} (required or optional) — click to require it`
                }
                className="cursor-pointer hover:opacity-70"
              >
                {name}
                {isRequired ? " (required)" : ""}
              </button>
              <button
                type="button"
                onClick={() => remove(name)}
                title={`Remove ${name}`}
                className="cursor-pointer hover:opacity-70"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {!isLoading && roles.length > 0 && (
        <div className="flex items-center px-2 text-[9px] uppercase tracking-wider opacity-40">
          <span className="flex-1">Role</span>
          <span className="shrink-0 w-12 text-center">Req.</span>
        </div>
      )}
      <div className="flex flex-col gap-0.5 max-h-72 overflow-y-auto">
        {isLoading && <div className="text-xs opacity-50 px-2 py-1">Loading…</div>}
        {!isLoading && roles.length === 0 && query && (
          <div className="text-xs opacity-50 px-2 py-1">No roles match.</div>
        )}
        {!isLoading &&
          roles.map(r => {
            const active = isSelected(r.name);
            const isRequired = required.includes(r.name);
            return (
              <div key={r.name} className="flex items-center">
                <button
                  type="button"
                  onClick={() => toggle(r.name)}
                  title={r.description ?? undefined}
                  className={twMerge(
                    "flex items-center gap-2 flex-1 min-w-0 text-left text-xs px-2 py-1 rounded transition-colors cursor-pointer",
                    active ? "bg-black/10 dark:bg-white/10 font-medium" : "hover:bg-black/5 dark:hover:bg-white/5"
                  )}
                >
                  <span className="size-3 shrink-0">{active && <CheckIcon className="size-3" />}</span>
                  <span className="truncate">{r.name}</span>
                </button>
                <span className="shrink-0 w-12 flex justify-center">
                  <input
                    type="checkbox"
                    checked={isRequired}
                    onChange={e => setRequired(r.name, e.target.checked)}
                    title={
                      isRequired
                        ? `Types where ${r.name} is required — untick to match any declaration`
                        : `Tick to only match types that REQUIRE ${r.name}`
                    }
                    className={twMerge(
                      "size-3.5 accent-brand-400 cursor-pointer transition-opacity",
                      isRequired ? "" : "opacity-30 hover:opacity-100"
                    )}
                  />
                </span>
              </div>
            );
          })}
      </div>
      {Boolean(rolesData?.next) && (
        <div className="text-[10px] text-amber-600 dark:text-amber-400 px-2">
          Showing first {PICKER_PAGE_SIZE} roles — narrow the search to find more.
        </div>
      )}
    </div>
  );
};

export const GroupTypesFilterSidebar: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const prefix = searchParams.get(PREFIX_PARAM) ?? "";

  // Local draft committed to the URL on Enter; re-sync when the URL changes
  // elsewhere (Clear / back nav).
  const [prefixDraft, setPrefixDraft] = useState(prefix);
  useEffect(() => setPrefixDraft(prefix), [prefix]);

  const update = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
    setSearchParams(next);
  };

  const anyActive =
    Boolean(prefix) ||
    Boolean(searchParams.get(REQUIRED_ROLES_PARAM)) ||
    Boolean(searchParams.get(ROLES_PARAM)) ||
    Boolean(searchParams.get(LEGACY_OPTIONAL_PARAM));

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
              next.delete(PREFIX_PARAM);
              next.delete(REQUIRED_ROLES_PARAM);
              next.delete(ROLES_PARAM);
              next.delete(LEGACY_OPTIONAL_PARAM);
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
              update(PREFIX_PARAM, prefixDraft || null);
            }}
            className="relative"
          >
            <MagnifyingGlassIcon className="size-3.5 absolute left-2 top-1/2 -translate-y-1/2 opacity-40" />
            <input
              type="text"
              value={prefixDraft}
              onChange={e => setPrefixDraft(e.target.value)}
              placeholder="e.g. product_  ↵"
              className="w-full text-xs pl-7 pr-2 py-1.5 rounded bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 outline-none focus:border-black/30 dark:focus:border-white/30"
            />
          </form>
        </div>

        <RolePicker />
      </div>
    </div>
  );
};
