import React, { createContext, useContext, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { Classifier } from "../api/client.schemas";
import { useClassifiersRetrieve } from "../api/client";

interface ClassifierDrawerContextType {
  isDrawerOpen: boolean;
  openDrawer: (slugVersion: string) => void;
  closeDrawer: () => void;
  classifierSlug: string;
  classifier: Classifier | undefined;
}

const ClassifierDrawerContext = createContext<ClassifierDrawerContextType | undefined>(undefined);

// ?peek=<slug>/<version> drawer, like the dataset one — the list stays mounted
// and the peeked classifier survives a reload or a shared link.
export function ClassifierDrawerProvider({ children }: { children: React.ReactNode }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const classifierSlug = searchParams.get("peek") || "";
  const isDrawerOpen = !!classifierSlug;

  const setPeek = (slugVersion: string | null) => {
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev);
        if (slugVersion) next.set("peek", slugVersion);
        else next.delete("peek");
        return next;
      },
      { replace: true }
    );
  };

  const { data: classifier, isError } = useClassifiersRetrieve(classifierSlug, {
    query: { enabled: isDrawerOpen },
  });

  useEffect(() => {
    if (isError) toast.error("Error loading classifier");
  }, [isError]);

  return (
    <ClassifierDrawerContext.Provider
      value={{
        isDrawerOpen,
        openDrawer: slugVersion => setPeek(slugVersion),
        closeDrawer: () => setPeek(null),
        classifierSlug,
        classifier,
      }}
    >
      {children}
    </ClassifierDrawerContext.Provider>
  );
}

export function useClassifierDrawer() {
  const context = useContext(ClassifierDrawerContext);
  if (context === undefined) {
    throw new Error("useClassifierDrawer must be used within a ClassifierDrawerProvider");
  }
  return context;
}
