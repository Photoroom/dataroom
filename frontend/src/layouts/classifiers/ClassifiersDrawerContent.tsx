import React from "react";
import { useClassifierDrawer } from "../../context/ClassifierDrawerContext";
import { ClassifierPeekPanel } from "../../components/classifier/ClassifierPeekPanel";

export const ClassifiersDrawerContent: React.FC = () => {
  const { classifier, closeDrawer } = useClassifierDrawer();

  if (!classifier) return <div className="p-4 text-sm opacity-50">Loading classifier...</div>;

  return <ClassifierPeekPanel classifier={classifier} onClose={closeDrawer} />;
};
