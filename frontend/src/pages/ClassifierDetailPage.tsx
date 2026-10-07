import React from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { twMerge } from "tailwind-merge";
import { useClassifiersRetrieve } from "../api/client";
import { MainContainer } from "../layouts/MainContainer";
import { ClassifierHeader } from "../components/classifier/ClassifierHeader";
import { ClassifierOverviewTab } from "../components/classifier/ClassifierOverviewTab";
import { ClassifierAnnotationsTab } from "../components/classifier/ClassifierAnnotationsTab";
import { ClassifierTrainingTab } from "../components/classifier/ClassifierTrainingTab";
import { ClassifierApplyTab } from "../components/classifier/ClassifierApplyTab";
import { ClassifierResultsTab } from "../components/classifier/ClassifierResultsTab";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "annotations", label: "Annotations" },
  { key: "training", label: "Training" },
  { key: "apply", label: "Apply" },
  { key: "results", label: "Results" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** A classifier's own page: one thing per tab.
 *
 * It is a page rather than an image grid. Browsing annotations is the images view, one
 * click away with the right filter. That keeps this page about the classifier
 * (what it is, what it learns from, what it did) instead of stacking every
 * action into one toolbar.
 */
export const ClassifierDetailPage: React.FC = () => {
  const { classifierSlug, classifierVersion } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const slugVersion = classifierSlug && classifierVersion ? `${classifierSlug}/${classifierVersion}` : "";
  const { data: classifier, refetch } = useClassifiersRetrieve(slugVersion, {
    query: { enabled: !!slugVersion },
  });

  const tab = (searchParams.get("tab") as TabKey) || "overview";
  const selectTab = (next: TabKey) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  if (!classifier) {
    return (
      <MainContainer isDrawerOpen={false}>
        <div className="p-6 text-sm opacity-50">Loading classifier...</div>
      </MainContainer>
    );
  }

  return (
    <MainContainer isDrawerOpen={false}>
      <div className="w-full max-w-5xl mx-auto p-3 sm:p-6 flex flex-col gap-5">
        <ClassifierHeader classifier={classifier} onChanged={refetch} />

        {/* A segmented control rather than underlined tabs: the underline sat on
            a -mb-px hairline and the active tab went bold, so switching tabs
            re-measured the row and nudged every label sideways. Constant weight,
            one moving surface. */}
        <nav className="inline-flex self-start gap-0.5 p-0.5 rounded-lg bg-black/5 dark:bg-white/5">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => selectTab(key)}
              aria-current={key === tab ? "page" : undefined}
              className={twMerge(
                "px-3 py-1.5 text-sm font-medium rounded-md cursor-pointer transition-colors",
                key === tab
                  ? "bg-white dark:bg-dark-100 shadow-sm"
                  : "opacity-50 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/5"
              )}
            >
              {label}
            </button>
          ))}
        </nav>

        {tab === "overview" && <ClassifierOverviewTab classifier={classifier} />}
        {tab === "annotations" && <ClassifierAnnotationsTab classifier={classifier} onChanged={refetch} />}
        {tab === "training" && <ClassifierTrainingTab classifier={classifier} />}
        {tab === "apply" && <ClassifierApplyTab classifier={classifier} onApplied={() => selectTab("results")} />}
        {tab === "results" && <ClassifierResultsTab classifier={classifier} />}
      </div>
    </MainContainer>
  );
};
