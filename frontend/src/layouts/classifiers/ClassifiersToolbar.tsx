import React, { useState } from "react";
import ReactDOM from "react-dom";
import { PlusIcon } from "@heroicons/react/24/outline";
import Popup from "../../components/common/Popup";
import { CreateClassifierForm } from "../../components/classifier/CreateClassifierForm";

export const ClassifiersToolbar: React.FC = () => {
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  return (
    <>
      <div className="flex-1" />
      <button type="button" className="btn btn-primary btn-sm shrink-0" onClick={() => setIsCreateOpen(true)}>
        <PlusIcon />
        <span className="hidden sm:inline">Create classifier</span>
      </button>

      {isCreateOpen &&
        ReactDOM.createPortal(
          <Popup onClose={() => setIsCreateOpen(false)}>
            <h5 className="mb-6">Create classifier</h5>
            <CreateClassifierForm onSuccess={() => setIsCreateOpen(false)} />
          </Popup>,
          document.body
        )}
    </>
  );
};
