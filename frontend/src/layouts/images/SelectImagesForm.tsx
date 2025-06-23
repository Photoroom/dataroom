import React from "react";
import ReactDOM from "react-dom";
import { useImageListData } from "../../context/ImageListDataContext";
import { LabelTooltip } from "../../components/forms/LabelTooltip";
import Popup from "../../components/common/Popup";
import { TagsForm } from "../../components/forms/TagsForm";
import { useTagsTagImagesUpdate } from "../../api/client";
import toast from "react-hot-toast";

export const SelectImagesForm: React.FC = () => {
  const { selectedImages, clearSelectedImages } = useImageListData();
  const [isAddTagsOpen, setIsAddTagsOpen] = React.useState(false);

  const selectedImagesString = `${selectedImages?.length || 0} selected image${selectedImages?.length === 1 ? '' : 's'}`;

  // -------------------- Clear selection --------------------
  const handleClearSelection = () => {
    if (confirm('Are you sure you want to clear the selection?')) {
      clearSelectedImages();
    }
  }

  // -------------------- Submit --------------------
  const { mutate: tagImages, isPending: isTaggingImages } = useTagsTagImagesUpdate();

  const handleTagsFormSubmit = (tags: string[]) => {
    if (selectedImages?.length === 0) {
      return;
    }
    tagImages({
      data: {
        image_ids: selectedImages,
        tag_names: tags,
      },
    }, {
      onSuccess: () => {
        setIsAddTagsOpen(false);
        toast.success(`Added tags to ${selectedImagesString}`);
      },
      onError: () => {
        toast.error('Error adding tags to images');
      },
    });
  }

  // -------------------- Render --------------------
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-row items-center justify-between gap-1">
        <p className="text-sm">Selected {selectedImagesString}.</p>
        <LabelTooltip content="Hold down the SHIFT key to select multiple images." />
      </div>
      <div className="flex flex-row gap-1">
        <button type="button" className="btn btn-primary btn-sm flex-1" disabled={selectedImages?.length === 0} onClick={() => { setIsAddTagsOpen(true) }}>Add tags</button>
        <button type="button" className="btn btn-outline btn-sm" disabled={selectedImages?.length === 0} onClick={handleClearSelection}>Clear</button>
      </div>

      {isAddTagsOpen && (
        ReactDOM.createPortal(
          <Popup onClose={() => { setIsAddTagsOpen(false); }}>
            <h5 className="mb-6">Add tags to {selectedImagesString}</h5>
            <TagsForm onSubmit={handleTagsFormSubmit} isLoading={isTaggingImages} />
          </Popup>,
          document.body
        )
      )}
    </div>
  );
};
