import React from "react";
import { Tag } from "../../api/client.schemas";
import { useTagsList } from "../../api/client";
import { TagInput } from "./TagInput";
import toast from "react-hot-toast";

interface TagsFormProps {
  initialTags?: string[];
  onSubmit: (tags: string[]) => void;
  isLoading: boolean;
}

export const TagsForm: React.FC<TagsFormProps> = ({ initialTags, onSubmit, isLoading }) => {
  const [selectedTags, setSelectedTags] = React.useState<string[]>(initialTags ?? []);

  // -------------------- Fetch tags --------------------
  const [availableTags, setAvailableTags] = React.useState<Tag[]>([]);
  const { data: tagsResponse, error: tagsError } = useTagsList();

  React.useEffect(() => {
    if (tagsResponse) {
      setAvailableTags(tagsResponse.results);
    }
  }, [tagsResponse]);

  React.useEffect(() => {
    if (tagsError) {
      toast.error("Error loading tags");
    }
  }, [tagsError]);

  // -------------------- Submit --------------------
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(selectedTags);
  };

  // -------------------- Render --------------------
  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <div>
        <TagInput
          value={selectedTags}
          onChange={value => {
            setSelectedTags(value);
          }}
          options={availableTags.map(tag => tag.name)}
        />
        <p className="text-xs opacity-60 mt-1">
          Press return, tab or space to add tags. Tags can only contain alphanumeric characters, dashes, and
          underscores.
        </p>
      </div>
      <button type="submit" className="btn btn-primary" disabled={isLoading}>
        Apply
      </button>
    </form>
  );
};
