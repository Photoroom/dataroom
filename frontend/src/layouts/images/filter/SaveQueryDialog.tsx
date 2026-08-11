import React, { useEffect, useState } from "react";
import toast from "react-hot-toast";
import Popup from "../../../components/common/Popup";
import { useQueriesCreate, useQueriesList, useQueriesPartialUpdate } from "../../../api/client";
import { useSettings } from "../../../context/SettingsContext";
import { useImageListData } from "../../../context/ImageListDataContext";
import { extractApiError } from "../../../api/errors";

// Slug must match the backend pattern ^[-a-zA-Z0-9_]+$ (max 100).
const slugify = (value: string): string =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);

const extractError = (error: unknown): string => extractApiError(error, "Error saving query");

const inputClass =
  "block w-full border bg-white border-black/20 text-black outline-none focus:ring-1 focus:border-primary-500 " +
  "focus:ring-primary-500 dark:border-white/10 dark:bg-black/20 dark:text-white p-1.5 px-2.5 text-sm rounded-lg";

interface SaveQueryDialogProps {
  /** The current image filters as API params (committedFilterParams). */
  filters: Record<string, unknown>;
  /** Slug of the saved query these filters are bound to (if any), for overwrite-on-save. */
  boundSlug?: string | null;
  onClose: () => void;
}

export const SaveQueryDialog: React.FC<SaveQueryDialogProps> = ({ filters, boundSlug, onClose }) => {
  const { user } = useSettings();
  const { bindQuery } = useImageListData();

  // The bound query (if any), used to prefill fields and check authorship. The list is
  // lightweight (no previews) and already cached from the search-bar dropdown.
  const { data: queryList } = useQueriesList({ page_size: 100 }, { query: { enabled: !!boundSlug } });
  const boundQuery = boundSlug ? queryList?.results.find(q => q.slug === boundSlug) : undefined;
  const isAuthor = !!boundQuery && boundQuery.author?.email === user.email;
  const canUpdate = !!boundQuery && isAuthor;

  const [mode, setMode] = useState<"update" | "create">("create");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [description, setDescription] = useState("");
  const [prefilled, setPrefilled] = useState(false);

  // Once the bound query loads, prefill from it and default to "update" mode (if allowed).
  useEffect(() => {
    if (prefilled || !boundQuery) return;
    setName(boundQuery.name);
    setSlug(boundQuery.slug);
    setSlugEdited(true); // don't auto-rewrite the slug from the name for an existing query
    setDescription(boundQuery.description ?? "");
    setMode(canUpdate ? "update" : "create");
    setPrefilled(true);
  }, [boundQuery, canUpdate, prefilled]);

  const { mutate: createQuery, isPending: isCreating } = useQueriesCreate();
  const { mutate: updateQuery, isPending: isUpdating } = useQueriesPartialUpdate();
  const isPending = isCreating || isUpdating;

  // Keep the slug in sync with the name until the user edits the slug themselves.
  const onNameChange = (value: string) => {
    setName(value);
    if (!slugEdited) setSlug(slugify(value));
  };

  const handleUpdate = () => {
    if (!boundSlug) return;
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("Name is required");
      return;
    }
    updateQuery(
      { slug: boundSlug, data: { name: trimmedName, description: description.trim(), filters } },
      {
        onSuccess: () => {
          toast.success(`Query "${trimmedName}" updated`);
          onClose();
        },
        onError: error => toast.error(extractError(error)),
      }
    );
  };

  const handleCreate = () => {
    const trimmedName = name.trim();
    const finalSlug = slug || slugify(trimmedName);
    if (!trimmedName || !finalSlug) {
      toast.error("Name is required");
      return;
    }
    createQuery(
      { data: { slug: finalSlug, name: trimmedName, description: description.trim(), filters } },
      {
        onSuccess: query => {
          toast.success(`Query "${query.name}" saved`);
          // Stay on the current chips, now bound to the new query (so the next Save can update it).
          bindQuery(query.slug);
          onClose();
        },
        onError: error => toast.error(extractError(error)),
      }
    );
  };

  return (
    <Popup onClose={onClose}>
      <div className="flex flex-col gap-4">
        <h3 className="text-lg font-bold">
          {mode === "update" && boundQuery ? `Update "${boundQuery.name}"` : "Save as query"}
        </h3>
        <p className="text-sm opacity-70">
          {mode === "update"
            ? "Overwrite this saved query with the current filters."
            : "Save the current image filters as a reusable, named query."}
        </p>

        {mode === "update" && boundQuery && (
          <p className="text-xs rounded-lg bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 p-2">
            This will overwrite the saved query "{boundQuery.name}" with your current filters.
          </p>
        )}

        {boundQuery && !isAuthor && (
          <p className="text-xs rounded-lg bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 p-2">
            You can only update queries you created. Saving will create a new query instead.
          </p>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium">Name</label>
          <input
            className={inputClass}
            value={name}
            onChange={e => onNameChange(e.target.value)}
            placeholder="e.g. Wide shutterstock images"
            autoFocus
          />
        </div>

        {mode === "create" && (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium">Slug</label>
            <input
              className={inputClass}
              value={slug}
              onChange={e => {
                setSlug(slugify(e.target.value));
                setSlugEdited(true);
              }}
              placeholder="wide-shutterstock-images"
            />
            <span className="text-[11px] opacity-50">
              Used in the URL (?query={slug || "slug"}). Letters, numbers, - and _.
            </span>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium">
            Description <span className="opacity-50">(optional)</span>
          </label>
          <textarea
            className={inputClass}
            rows={2}
            value={description}
            onChange={e => setDescription(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-2 justify-end">
          {/* Toggle between updating the bound query and saving a brand-new one. */}
          {canUpdate && (
            <button
              type="button"
              className="text-xs opacity-70 hover:opacity-100 underline mr-auto"
              onClick={() => setMode(m => (m === "update" ? "create" : "update"))}
              disabled={isPending}
            >
              {mode === "update" ? "Save as new instead" : "Back to update"}
            </button>
          )}
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={isPending}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={mode === "update" ? handleUpdate : handleCreate}
            disabled={isPending || !name.trim()}
          >
            {isPending ? "Saving..." : mode === "update" && boundQuery ? "Update" : "Save query"}
          </button>
        </div>
      </div>
    </Popup>
  );
};
