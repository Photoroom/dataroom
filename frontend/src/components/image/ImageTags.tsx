import React, { useState } from "react";
import ReactDOM from "react-dom";
import { OSImage } from "../../api/client.schemas";
import Popup from "../common/Popup";
import { Collapsible } from "../common/Collapsible";
import { PlusIcon } from "@heroicons/react/24/outline";
import { LoaderSkeleton } from "../common/LoaderSkeleton";
import { TagsForm } from "../forms/TagsForm";
import { useImageDrawer } from "../../context/ImageDrawerContext";
import { useImagesUpdate } from "../../api/client";
import toast from "react-hot-toast";

interface ImageTagsProps {
  image?: OSImage;
  enableEdit?: boolean;
}

export const ImageTags: React.FC<ImageTagsProps> = ({ 
  image,
  enableEdit = true,
}) => {
  const [isAddTagsOpen, setIsAddTagsOpen] = useState(false);
  const { refetchImage } = useImageDrawer();

  // -------------------- Submit --------------------
  const { mutate: updateImage, isPending: isUpdatingImage } = useImagesUpdate();

  const handleTagsFormSubmit = (tags: string[]) => {
      if (!image) {
        return;
      }
      updateImage({
        id: image.id,
        data: {
          tags: tags,
        },
      }, {
        onSuccess: () => {
          setIsAddTagsOpen(false);
          refetchImage();
        },
        onError: () => {
          toast.error("Error updating image tags");
        },
      });
  };

  // -------------------- Render --------------------
  return (
    <Collapsible name="tags" title="Tags" initialOpen={true}>
      <div className="flex flex-row flex-wrap items-center gap-2">
        {
          image ? (
            <>
              {image.tags && !!image.tags.length && image.tags.map((tag: string) => (
                <span className="px-3 py-1 rounded-full text-xs text-left bg-black/8 dark:bg-white/8" key={tag}>{tag}</span>
              ))}
              {!image.tags || image.tags?.length === 0 && (
                <p className="opacity-50">No tags</p>
              )}
            </>
          ) : (
            <>
              <LoaderSkeleton className="w-20" />
              <LoaderSkeleton className="w-20" />
            </>
          )
        }
        {enableEdit && (
          <button 
            type="button"
            onClick={() => { setIsAddTagsOpen(true) }}
            className="px-3 py-1 cursor-pointer border border-black/8 dark:border-white/8 rounded-full hover:bg-black/8 dark:hover:bg-white/8"
            key="+"
            title="Add tag"
          ><PlusIcon className="size-4" /></button>
        )}
      </div>

      {enableEdit && image && isAddTagsOpen && (
        ReactDOM.createPortal(
          <Popup onClose={() => { setIsAddTagsOpen(false); }}>
            <h5 className="mb-6">Add tags to {image.id}</h5>
            <TagsForm initialTags={image.tags} onSubmit={handleTagsFormSubmit} isLoading={isUpdatingImage} />
          </Popup>,
          document.body
        )
      )}
    </Collapsible>
  );
}; 
