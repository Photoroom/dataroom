import React from "react";
import {
  useDatasetsList,
  useDatasetsCreate,
  useDatasetsImagesCreate,
  useDatasetsGroupsCreate,
  useDatasetsCopyCreate,
} from "../../api/client";
import { Dataset } from "../../api/client.schemas";
import { TextField } from "../forms/TextField";
import { formatNumber } from "../../utils/formatNumber";
import { extractApiError } from "../../api/errors";
import toast from "react-hot-toast";

// Mirrors DATASET_UPDATE_GROUPS_LIMIT in backend/dataroom/models/dataset.py.
export const DATASET_MEMBER_UPDATE_LIMIT = 100;

// Add images or groups to a dataset — same form, only the noun + endpoint
// differ (images -> single_image datasets, groups -> datasets of their own type).
interface AddToDatasetFormProps {
  ids: string[];
  noun: "image" | "group";
  datasetType: string;
  onSuccess?: () => void;
}

export const AddToDatasetForm: React.FC<AddToDatasetFormProps> = ({ ids, noun, datasetType, onSuccess }) => {
  const { data: datasetsResponse } = useDatasetsList({ page_size: 200, type: datasetType });
  const [mode, setMode] = React.useState<"select" | "create">("select");
  const [selectedSlug, setSelectedSlug] = React.useState("");

  const [newSlugEdited, setNewSlugEdited] = React.useState(false);
  const [newSlug, setNewSlug] = React.useState("");
  const [newName, setNewName] = React.useState("");
  const [newDescription, setNewDescription] = React.useState("");
  const [copyFromVersion, setCopyFromVersion] = React.useState("");
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  const nouns = ids.length === 1 ? noun : `${noun}s`;
  const slugify = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^a-z0-9-]/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 32);

  const { mutate: createDataset, isPending: isCreating } = useDatasetsCreate();
  const { mutate: addImages, isPending: isAddingImages } = useDatasetsImagesCreate();
  const { mutate: addGroups, isPending: isAddingGroups } = useDatasetsGroupsCreate();
  const { mutate: copyDataset, isPending: isCopying } = useDatasetsCopyCreate();

  const datasetsBySlug = React.useMemo(() => {
    if (!datasetsResponse?.results) return {};
    const grouped: Record<string, Dataset[]> = {};
    for (const d of datasetsResponse.results) {
      if (!grouped[d.slug]) grouped[d.slug] = [];
      grouped[d.slug].push(d);
    }
    for (const slug of Object.keys(grouped)) {
      grouped[slug].sort((a, b) => b.version - a.version);
    }
    return grouped;
  }, [datasetsResponse]);

  const datasetSlugs = React.useMemo(() => {
    return Object.entries(datasetsBySlug).map(([slug, versions]) => ({
      slug,
      latest: versions[0],
      versions,
    }));
  }, [datasetsBySlug]);

  const selectedEntry = datasetSlugs.find(e => e.slug === selectedSlug);
  const latestIsFrozen = selectedEntry?.latest.is_frozen;

  const [isNewVersionMode, setIsNewVersionMode] = React.useState(false);

  React.useEffect(() => {
    if (selectedEntry && latestIsFrozen) {
      setIsNewVersionMode(true);
      setNewSlug(selectedEntry.latest.slug);
      setNewName(selectedEntry.latest.name);
      setNewDescription(selectedEntry.latest.description ?? "");
      setCopyFromVersion("");
    } else {
      setIsNewVersionMode(false);
    }
  }, [selectedSlug]);

  const addToDataset = (slugVersion: string) => {
    const handlers = {
      onSuccess: (res: { updated_count: number }) => {
        toast.success(`Added ${res.updated_count} ${res.updated_count === 1 ? noun : `${noun}s`} to dataset`);
        onSuccess?.();
      },
      onError: (e: unknown) => toast.error(extractApiError(e, `Error adding ${noun}s to dataset`)),
    };
    if (noun === "image") addImages({ slugVersion, data: { image_ids: ids } }, handlers);
    else addGroups({ slugVersion, data: { group_ids: ids } }, handlers);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (mode === "select") {
      if (!selectedSlug) {
        setErrors({ dataset: "Select a dataset" });
        return;
      }
      if (latestIsFrozen && isNewVersionMode) {
        handleCreateNewVersion();
      } else if (selectedEntry) {
        addToDataset(selectedEntry.latest.slug_version);
      }
    } else {
      handleCreateBrandNew();
    }
  };

  const handleCreateNewVersion = () => {
    const entry = selectedEntry;
    if (!entry) return;

    if (copyFromVersion) {
      copyDataset(
        {
          slugVersion: copyFromVersion,
          data: { slug: entry.latest.slug, name: entry.latest.name, description: entry.latest.description },
        },
        {
          onSuccess: created => {
            toast.success(`v${created.version} created with ${created.group_count} copied ${noun}s`);
            addToDataset(created.slug_version);
          },
          onError: (e: unknown) => toast.error(extractApiError(e, "Error creating new version")),
        }
      );
    } else {
      createDataset(
        {
          data: {
            slug: entry.latest.slug,
            name: entry.latest.name,
            description: entry.latest.description,
            type: datasetType,
          },
        },
        {
          onSuccess: created => {
            toast.success(`New version v${created.version} created`);
            addToDataset(created.slug_version);
          },
          onError: (e: unknown) => toast.error(extractApiError(e, "Error creating new version")),
        }
      );
    }
  };

  const handleCreateBrandNew = () => {
    const newErrors: Record<string, string> = {};
    if (!newSlug) {
      newErrors.slug = "Slug is required";
    } else if (!/^[-a-zA-Z0-9_]+$/.test(newSlug)) {
      newErrors.slug = "Only letters, numbers, dashes and underscores";
    }
    if (!newName) {
      newErrors.name = "Name is required";
    } else if (newName.length > 100) {
      newErrors.name = "Max 100 characters";
    }
    if (datasetsBySlug[newSlug]) {
      newErrors.slug = "A dataset with this slug already exists";
    }
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }
    setErrors({});

    createDataset(
      { data: { slug: newSlug, name: newName, description: newDescription || undefined, type: datasetType } },
      {
        onSuccess: created => addToDataset(created.slug_version),
        onError: (e: unknown) => toast.error(extractApiError(e, "Error creating dataset")),
      }
    );
  };

  const isPending = isCreating || isAddingImages || isAddingGroups || isCopying;
  const overLimit = ids.length > DATASET_MEMBER_UPDATE_LIMIT;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex gap-2">
        <button
          type="button"
          className={`btn btn-sm flex-1 ${mode === "select" ? "btn-primary" : "btn-outline"}`}
          onClick={() => {
            setMode("select");
            setErrors({});
          }}
        >
          Existing dataset
        </button>
        <button
          type="button"
          className={`btn btn-sm flex-1 ${mode === "create" ? "btn-primary" : "btn-outline"}`}
          onClick={() => {
            setMode("create");
            setErrors({});
          }}
        >
          New dataset
        </button>
      </div>

      {mode === "select" ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <select
              className="block w-full border bg-white border-black/20 text-black outline-none focus:ring-1 focus:border-primary-500 focus:ring-primary-500 dark:border-white/10 dark:bg-black/20 dark:text-white p-1.5 px-2.5 text-sm rounded-lg"
              value={selectedSlug}
              onChange={e => {
                setSelectedSlug(e.target.value);
                setErrors({});
              }}
            >
              <option value="">Select a dataset...</option>
              {datasetSlugs.map(entry => (
                <option key={entry.slug} value={entry.slug}>
                  {entry.latest.name} ({entry.slug}) — v{entry.latest.version}
                  {entry.latest.is_frozen ? " (frozen)" : ""} [{formatNumber(entry.latest.group_count, { decimals: 0 })}
                  ]
                </option>
              ))}
            </select>
            {errors.dataset && <span className="text-sm text-rose-500 dark:text-rose-400">{errors.dataset}</span>}
          </div>

          {latestIsFrozen && selectedEntry && (
            <div className="flex flex-col gap-3 p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
              <p className="text-xs opacity-70">
                Latest version (v{selectedEntry.latest.version}) is frozen. A new version will be created.
              </p>

              {selectedEntry.versions.length > 0 && (
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium">Copy {noun}s from version</label>
                  <select
                    className="block w-full border bg-white border-black/20 text-black outline-none focus:ring-1 focus:border-primary-500 focus:ring-primary-500 dark:border-white/10 dark:bg-black/20 dark:text-white p-1.5 px-2.5 text-sm rounded-lg"
                    value={copyFromVersion}
                    onChange={e => setCopyFromVersion(e.target.value)}
                  >
                    <option value="">Don't copy {noun}s</option>
                    {selectedEntry.versions.map(v => (
                      <option key={v.version} value={v.slug_version}>
                        v{v.version}
                        {v.is_frozen ? " (frozen)" : ""} — {formatNumber(v.group_count, { decimals: 0 })} {noun}s
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <>
          <TextField
            label="Name"
            name="name"
            value={newName}
            onChange={e => {
              setNewName(e.target.value);
              if (!newSlugEdited) setNewSlug(slugify(e.target.value));
            }}
            placeholder="My Dataset"
            error={errors.name}
          />
          <TextField
            label="Slug"
            name="slug"
            value={newSlug}
            onChange={e => {
              setNewSlugEdited(true);
              setNewSlug(e.target.value);
            }}
            placeholder="my-dataset"
            error={errors.slug}
            helpText="Unique identifier. Letters, numbers, dashes, underscores only."
          />
          <div className="flex flex-col gap-1">
            <label htmlFor="id_new_typed_description" className="text-sm font-medium">
              Description
            </label>
            <textarea
              id="id_new_typed_description"
              value={newDescription}
              onChange={e => setNewDescription(e.target.value)}
              placeholder="Optional description..."
              rows={2}
              className="block w-full border bg-white border-black/20 text-black placeholder-black/20 outline-none focus:ring-1 focus:border-primary-500 focus:ring-primary-500 dark:border-white/10 dark:bg-black/20 dark:text-white dark:placeholder-white/20 p-1.5 px-2.5 text-sm rounded-lg"
            />
          </div>
        </>
      )}

      {overLimit && (
        <span className="text-sm text-rose-500 dark:text-rose-400">
          You can add at most {DATASET_MEMBER_UPDATE_LIMIT} {noun}s to a dataset at a time ({ids.length} selected).
        </span>
      )}
      <button type="submit" className="btn btn-primary" disabled={isPending || overLimit}>
        {isCopying ? `Copying ${noun}s...` : isPending ? "Adding..." : `Add ${ids.length} ${nouns} to dataset`}
      </button>
    </form>
  );
};
