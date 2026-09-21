import React from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { useClassifiersCreate, useDatasetsList, getClassifiersListQueryKey } from "../../api/client";
import { TextField, formWidgetClassName } from "../forms/TextField";
import { extractApiError } from "../../api/errors";
import { URLS } from "../../urls";
import { EMBEDDING_SPACES } from "../../embeddingSpaces";
import { EmbeddingSpaceEnum } from "../../api/client.schemas";

import { slugify } from "../dataset/CreateDatasetForm";

// One side of the classifier: pick an existing single_image dataset to hold the
// annotations, or let the form create a fresh one (default).
const AnnotationSetField: React.FC<{
  side: "positive" | "negative";
  mode: "create" | "select";
  setMode: (mode: "create" | "select") => void;
  selected: string;
  setSelected: (slugVersion: string) => void;
  newSlug: string;
  error?: string;
}> = ({ side, mode, setMode, selected, setSelected, newSlug, error }) => {
  const { data: datasets } = useDatasetsList({ page_size: 200, type: "single_image" });

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium capitalize">{side} annotations</label>
        <div className="flex gap-1">
          <button
            type="button"
            className={`btn btn-sm ${mode === "create" ? "btn-primary" : "btn-outline"}`}
            onClick={() => setMode("create")}
          >
            New
          </button>
          <button
            type="button"
            className={`btn btn-sm ${mode === "select" ? "btn-primary" : "btn-outline"}`}
            onClick={() => setMode("select")}
          >
            Existing
          </button>
        </div>
      </div>
      {mode === "create" ? (
        <p className="text-xs opacity-60">
          A new dataset <code className="font-mono">{newSlug || "..."}</code> will be created.
        </p>
      ) : (
        <select className={formWidgetClassName} value={selected} onChange={e => setSelected(e.target.value)}>
          <option value="">Select a dataset...</option>
          {datasets?.results?.map(d => (
            <option key={d.slug_version} value={d.slug_version}>
              {d.name} ({d.slug_version}) [{d.group_count}]
            </option>
          ))}
        </select>
      )}
      {error && <span className="text-sm text-rose-500 dark:text-rose-400">{error}</span>}
    </div>
  );
};

export const CreateClassifierForm: React.FC<{ onSuccess?: () => void }> = ({ onSuccess }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = React.useState("");
  const [slug, setSlug] = React.useState("");
  const [slugEdited, setSlugEdited] = React.useState(false);
  const [description, setDescription] = React.useState("");
  const [embeddingSpace, setEmbeddingSpace] = React.useState("");
  const [posMode, setPosMode] = React.useState<"create" | "select">("create");
  const [negMode, setNegMode] = React.useState<"create" | "select">("create");
  const [posSelected, setPosSelected] = React.useState("");
  const [negSelected, setNegSelected] = React.useState("");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [isPending, setIsPending] = React.useState(false);

  const { mutateAsync: createClassifier } = useClassifiersCreate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Record<string, string> = {};
    if (!name) newErrors.name = "Name is required";
    if (!slug) newErrors.slug = "Slug is required";
    else if (!/^[-a-zA-Z0-9_]+$/.test(slug)) newErrors.slug = "Only letters, numbers, dashes and underscores";
    if (posMode === "select" && !posSelected) newErrors.pos = "Select a dataset";
    if (negMode === "select" && !negSelected) newErrors.neg = "Select a dataset";
    // Required, not optional: a blank space used to reach the pipeline as ""
    // and be resolved there to a default the form never showed.
    if (!embeddingSpace) newErrors.embedding_space = "Select an embedding space";
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }
    setErrors({});
    setIsPending(true);
    try {
      // A side left out is created by the server as <slug>-positives /
      // <slug>-negatives, reusing those datasets if they already exist. Creating
      // them here instead would make a NEW version of them every time, so a
      // second classifier version would start from empty buckets.
      const classifier = await createClassifier({
        data: {
          slug,
          name,
          description: description || undefined,
          embedding_space: embeddingSpace as EmbeddingSpaceEnum,
          ...(posMode === "select" ? { pos_datasets: [posSelected] } : {}),
          ...(negMode === "select" ? { neg_datasets: [negSelected] } : {}),
        },
      });
      queryClient.invalidateQueries({ queryKey: getClassifiersListQueryKey() });
      toast.success(`Classifier "${name}" created`);
      onSuccess?.();
      navigate(URLS.CLASSIFIER_DETAIL(classifier.slug, classifier.version));
    } catch (e) {
      toast.error(extractApiError(e, "Error creating classifier"));
    } finally {
      setIsPending(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <TextField
        label="Name"
        name="name"
        value={name}
        onChange={e => {
          setName(e.target.value);
          if (!slugEdited) setSlug(slugify(e.target.value));
        }}
        placeholder="Studio shots"
        error={errors.name}
      />
      <TextField
        label="Slug"
        name="slug"
        value={slug}
        onChange={e => {
          setSlugEdited(true);
          setSlug(e.target.value);
        }}
        placeholder="studio-shots"
        error={errors.slug}
        helpText="Unique identifier. Reusing an existing slug creates the next version."
      />
      <div className="flex flex-col gap-1">
        <label htmlFor="id_classifier_description" className="text-sm font-medium">
          Description
        </label>
        <textarea
          id="id_classifier_description"
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="What counts as a positive?"
          rows={2}
          className="block w-full border bg-white border-black/20 text-black placeholder-black/20 outline-none focus:ring-1 focus:border-brand-500 focus:ring-brand-500 dark:border-white/10 dark:bg-black/20 dark:text-white dark:placeholder-white/20 p-1.5 px-2.5 text-sm rounded-lg"
        />
      </div>
      <AnnotationSetField
        side="positive"
        mode={posMode}
        setMode={setPosMode}
        selected={posSelected}
        setSelected={setPosSelected}
        newSlug={slug ? `${slug}-positives` : ""}
        error={errors.pos}
      />
      <AnnotationSetField
        side="negative"
        mode={negMode}
        setMode={setNegMode}
        selected={negSelected}
        setSelected={setNegSelected}
        newSlug={slug ? `${slug}-negatives` : ""}
        error={errors.neg}
      />
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium" htmlFor="embedding_space">
          Embedding space
        </label>
        <select
          id="embedding_space"
          name="embedding_space"
          className={formWidgetClassName}
          value={embeddingSpace}
          onChange={e => setEmbeddingSpace(e.target.value)}
        >
          <option value="">Select an embedding space...</option>
          {EMBEDDING_SPACES.map(space => (
            <option key={space.value} value={space.value}>
              {space.label}
            </option>
          ))}
        </select>
        <span className="text-xs opacity-60">
          Which image embedding a model for this classifier is trained on. Images without a vector in this space are
          embedded on the first run, which for a large set takes a while.
        </span>
        {errors.embedding_space && (
          <span className="text-sm text-rose-500 dark:text-rose-400">{errors.embedding_space}</span>
        )}
      </div>
      <button type="submit" className="btn btn-primary" disabled={isPending}>
        {isPending ? "Creating..." : "Create classifier"}
      </button>
    </form>
  );
};
