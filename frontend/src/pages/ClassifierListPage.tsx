import React, { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "react-hot-toast";
import { LockClosedIcon } from "@heroicons/react/24/outline";
import { twMerge } from "tailwind-merge";
import { MainContainer } from "../layouts/MainContainer";
import { useClassifiersList } from "../api/client";
import { Classifier } from "../api/client.schemas";
import { Card } from "../components/common/Card";
import { LoaderSkeleton } from "../components/common/LoaderSkeleton";
import { useClassifierDrawer } from "../context/ClassifierDrawerContext";

export const AnnotationCounts: React.FC<{ pos: number; neg: number }> = ({ pos, neg }) => (
  <div className="flex gap-1.5 text-[11px]">
    <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 tabular-nums">
      +{pos}
    </span>
    <span className="px-1.5 py-0.5 rounded-full bg-rose-500/15 text-rose-700 dark:text-rose-400 tabular-nums">
      -{neg}
    </span>
  </div>
);

/** A dense text card: what you scan a list of classifiers for is names, sizes
 * and state. Clicking opens the peek panel, where pictures belong. */
const ClassifierCard: React.FC<{ classifier: Classifier; isActive: boolean; onSelect: () => void }> = ({
  classifier,
  isActive,
  onSelect,
}) => {
  const counts = classifier.counts;
  return (
    <button type="button" onClick={onSelect} className="text-left">
      <Card
        className={twMerge(
          "flex-col gap-1.5 p-3 h-full cursor-pointer transition-colors",
          isActive ? "border-brand-400" : "hover:border-brand-400/60"
        )}
      >
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold truncate">{classifier.name}</span>
          {classifier.is_frozen && <LockClosedIcon className="w-3 h-3 opacity-50 shrink-0" />}
          <div className="flex-1" />
          <span className="text-[11px] opacity-40 tabular-nums shrink-0">v{classifier.version}</span>
        </div>

        <AnnotationCounts pos={counts.pos} neg={counts.neg} />

        {/* What this version is for. With all_versions on, a column of cards
            differing only by number is unreadable without it. */}
        {classifier.version_note && (
          <p className="text-[11px] opacity-60 line-clamp-2" title={classifier.version_note}>
            {classifier.version_note}
          </p>
        )}

        <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-[11px] opacity-50 tabular-nums">
          <dt>main</dt>
          <dd className="text-right">
            {counts.main_pos}/{counts.main_neg}
          </dd>
          <dt>additional</dt>
          <dd className="text-right">
            {counts.extra_pos}/{counts.extra_neg}
          </dd>
          <dt>updated</dt>
          <dd className="text-right">{new Date(classifier.date_updated).toLocaleDateString()}</dd>
        </dl>

        {classifier.embedding_space && (
          <span className="text-[11px] font-mono opacity-40 truncate">{classifier.embedding_space}</span>
        )}
      </Card>
    </button>
  );
};

export const ClassifierListPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const showAllVersions = searchParams.get("all_versions") === "1";
  const namePrefix = searchParams.get("name__prefix") || undefined;
  const { data, isLoading, isError } = useClassifiersList({ name__prefix: namePrefix });
  const { isDrawerOpen, classifierSlug: peeked, openDrawer, closeDrawer } = useClassifierDrawer();

  useEffect(() => {
    if (isError) toast.error("Error loading classifiers");
  }, [isError]);

  // Default view collapses each slug to its latest version, matching the
  // datasets list; ?all_versions=1 lists every version as its own card.
  const classifiers = useMemo(() => {
    const results = data?.results ?? [];
    if (showAllVersions) return results;
    const latest: Record<string, Classifier> = {};
    for (const classifier of results) {
      if (classifier.version > (latest[classifier.slug]?.version || 0)) {
        latest[classifier.slug] = classifier;
      }
    }
    return results.filter(c => latest[c.slug] === c);
  }, [data?.results, showAllVersions]);

  return (
    <MainContainer isDrawerOpen={isDrawerOpen} isSidebarOpen>
      <div className="w-full">
        {isLoading && (
          <div className="grid gap-3 p-3 sm:p-6 grid-cols-2 sm:grid-cols-4 lg:grid-cols-6">
            {Array.from({ length: 12 }).map((_, i) => (
              <Card key={i} className="flex-col gap-2 p-3">
                <LoaderSkeleton className="h-3 w-3/4" />
                <LoaderSkeleton className="h-3 w-1/2" />
              </Card>
            ))}
          </div>
        )}
        {!isLoading && classifiers.length === 0 && (
          <p className="text-sm opacity-50 p-4">
            No classifiers yet. Use <strong>Create classifier</strong> to add one, then collect positive and negative
            annotation images into it.
          </p>
        )}
        {!isLoading && classifiers.length > 0 && (
          <div className="grid gap-3 p-3 sm:p-6 grid-cols-2 sm:grid-cols-4 lg:grid-cols-6">
            {classifiers.map(classifier => (
              <ClassifierCard
                key={classifier.slug_version}
                classifier={classifier}
                isActive={classifier.slug_version === peeked}
                onSelect={() =>
                  classifier.slug_version === peeked ? closeDrawer() : openDrawer(classifier.slug_version)
                }
              />
            ))}
          </div>
        )}
      </div>
    </MainContainer>
  );
};
