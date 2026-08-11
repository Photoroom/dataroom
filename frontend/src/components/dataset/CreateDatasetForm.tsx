import React from "react";
import { TextField } from "../forms/TextField";
import { datasetsList, getDatasetsListQueryKey, useDatasetsCreate, useGroupTypesList } from "../../api/client";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { URLS } from "../../urls";

interface CreateDatasetFormProps {
  onSuccess?: () => void;
}

export const CreateDatasetForm: React.FC<CreateDatasetFormProps> = ({ onSuccess }) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = React.useState("");
  const [slug, setSlug] = React.useState("");
  const [slugEdited, setSlugEdited] = React.useState(false);
  const [type, setType] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  const { data: groupTypes } = useGroupTypesList({ page_size: 100 });
  const types = groupTypes?.results ?? [];

  // Auto-generate slug from name: lowercase, dashes only, max 32 chars to keep URLs short
  const slugify = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^a-z0-9-]/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 32);

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setName(e.target.value);
    if (!slugEdited) setSlug(slugify(e.target.value));
  };

  const handleSlugChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSlugEdited(true);
    setSlug(e.target.value);
  };

  const { mutate: createDataset, isPending } = useDatasetsCreate();

  const validate = () => {
    const newErrors: Record<string, string> = {};
    if (!slug) {
      newErrors.slug = "Slug is required";
    } else if (!/^[a-z0-9-]+$/.test(slug)) {
      newErrors.slug = "Only lowercase letters, numbers and dashes";
    }
    if (!name) {
      newErrors.name = "Name is required";
    } else if (name.length > 100) {
      newErrors.name = "Max 100 characters";
    }
    if (!type) {
      newErrors.type = "Type is required";
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    const existing = await datasetsList({ slug, page_size: 1 });
    if (existing.results.length > 0) {
      setErrors({ slug: "A dataset with this slug already exists" });
      return;
    }

    createDataset(
      { data: { slug, name, type, description: description || undefined } },
      {
        onSuccess: created => {
          toast.success(`Dataset "${name}" created`);
          queryClient.invalidateQueries({ queryKey: getDatasetsListQueryKey() });
          onSuccess?.();
          navigate(URLS.DATASET_DETAIL(created.slug, created.version));
        },
        onError: () => {
          toast.error("Error creating dataset");
        },
      }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <TextField
        label="Name"
        name="name"
        value={name}
        onChange={handleNameChange}
        placeholder="My Dataset"
        error={errors.name}
      />
      <TextField
        label="Slug"
        name="slug"
        value={slug}
        onChange={handleSlugChange}
        placeholder="my-dataset"
        error={errors.slug}
        helpText="Unique identifier. Lowercase letters, numbers and dashes only."
      />
      <div className="flex flex-col gap-1">
        <label htmlFor="id_type" className="text-sm font-medium">
          Type
        </label>
        <select
          id="id_type"
          name="type"
          value={type}
          onChange={e => setType(e.target.value)}
          className="block w-full border bg-white border-black/20 text-black outline-none focus:ring-1 focus:border-primary-500 focus:ring-primary-500 dark:border-white/10 dark:bg-black/20 dark:text-white p-1.5 px-2.5 text-sm rounded-lg"
        >
          <option value="">Select a type...</option>
          {types.map(t => (
            <option key={t.name} value={t.name}>
              {t.name}
            </option>
          ))}
        </select>
        {errors.type && <p className="text-xs text-rose-500">{errors.type}</p>}
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="id_description" className="text-sm font-medium">
          Description
        </label>
        <textarea
          id="id_description"
          name="description"
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Optional description..."
          rows={3}
          className="block w-full border bg-white border-black/20 text-black placeholder-black/20 outline-none focus:ring-1 focus:border-primary-500 focus:ring-primary-500 dark:border-white/10 dark:bg-black/20 dark:text-white dark:placeholder-white/20 p-1.5 px-2.5 text-sm rounded-lg"
        />
      </div>
      <button type="submit" className="btn btn-primary" disabled={isPending}>
        {isPending ? "Creating..." : "Create dataset"}
      </button>
    </form>
  );
};
