import React, { useEffect, useState } from "react";
import { ChoiceFilter } from "./ChoiceFilter";
import { useStatsAttributesList, useStatsImageAspectRatioFractionsRetrieve, useStatsImageSourcesRetrieve, useStatsLatentTypesList, useTagsList } from "../../api/client";
import toast from "react-hot-toast";
import { useImageListData } from "../../context/ImageListDataContext";

export const Filters: React.FC = () => {
  const { filters, setFilters } = useImageListData();

  // -------------------- Sources --------------------
  const [sources, setSources] = useState<string[]>(filters.sources);
  const { data: allSources, isLoading: isLoadingSources, isError: isErrorSources } = useStatsImageSourcesRetrieve();

  useEffect(() => {
    if (isErrorSources) {
      toast.error("Error loading image sources");
    }
  }, [isErrorSources]);

  // -------------------- Tags --------------------
  const [tags, setTags] = useState<string[]>(filters.tags);
  const { data: allTags, isLoading: isLoadingTags, isError: isErrorTags } = useTagsList();

  useEffect(() => {
    if (isErrorTags) {
      toast.error("Error loading image tags");
    }
  }, [isErrorTags]);

  // -------------------- Aspect Ratio --------------------
  const [aspectRatio, setAspectRatio] = useState<string | null>(filters.aspect_ratio_fraction);
  const { data: allAspectRatios, isLoading: isLoadingAspectRatios, isError: isErrorAspectRatios } = useStatsImageAspectRatioFractionsRetrieve();

  useEffect(() => {
    if (isErrorAspectRatios) {
      toast.error("Error loading image aspect ratios");
    }
  }, [isErrorAspectRatios]);

  // -------------------- Atributes --------------------
  const [attributes, setAttributes] = useState<string[]>(filters.has_attributes);
  const { data: allAttributes, isLoading: isLoadingAttributes, isError: isErrorAttributes } = useStatsAttributesList();

  useEffect(() => {
    if (isErrorAttributes) {
      toast.error("Error loading image attributes");
    }
  }, [isErrorAttributes]);

  // -------------------- Latents --------------------
  const [latents, setLatents] = useState<string[]>(filters.has_latents);
  const { data: allLatents, isLoading: isLoadingLatents, isError: isErrorLatents } = useStatsLatentTypesList();

  useEffect(() => {
    if (isErrorLatents) {
      toast.error("Error loading image latents");
    }
  }, [isErrorLatents]);

  // -------------------- Duplicate State --------------------
  const [duplicateState, setDuplicateState] = useState<string | null>(filters.duplicate_state);
  const duplicateStateChoices = [
    {label: 'Unprocessed', value: 'None'},
    {label: 'Original', value: '1'},
    {label: 'Duplicate', value: '2'},
  ]

  // -------------------- URL --------------------

  useEffect(() => {
    const newFilters = {
      sources: sources.length > 0 ? sources : [],
      tags: tags.length > 0 ? tags : [],
      aspect_ratio_fraction: aspectRatio ? aspectRatio : null,
      has_attributes: attributes.length > 0 ? attributes : [],
      has_latents: latents.length > 0 ? latents : [],
      duplicate_state: duplicateState ? duplicateState : null,
    };
    setFilters(newFilters);
  }, [sources, tags, aspectRatio, attributes, latents, duplicateState])

  // -------------------- Render --------------------
  return (
    <div className="flex flex-col gap-4 px-1 pt-2 border-t border-black/10 dark:border-white/10">
      <ChoiceFilter
        label="Source"
        isLoading={isLoadingSources}
        choices={Object.entries(allSources || {}).map(([value, count]) => ({
          value,
          count,
        }))}
        selected={sources}
        onChange={(selected) => setSources(selected)}
        allowMultiple={true}
      />
      <ChoiceFilter
        label="Tags"
        isLoading={isLoadingTags}
        choices={allTags?.results.map((tag) => ({
          value: tag.name,
          count: tag.image_count,
        })) || []}
        selected={tags}
        onChange={(selected) => setTags(selected)}
        allowMultiple={true}
      />
      <ChoiceFilter
        label="Aspect Ratio"
        isLoading={isLoadingAspectRatios}
        choices={Object.entries(allAspectRatios || {}).map(([value, count]) => ({
          value,
          count,
        }))}
        selected={aspectRatio ? [aspectRatio] : []}
        onChange={(selected) => setAspectRatio(selected[0])}
        allowMultiple={false}
      />
      <ChoiceFilter
        label="Attributes"
        isLoading={isLoadingAttributes}
        choices={allAttributes?.map((attribute) => ({
          value: attribute.name,
          count: attribute.image_count,
        })) || []}
        selected={attributes}
        onChange={(selected) => setAttributes(selected)}
        allowMultiple={true}
      />
      <ChoiceFilter
        label="Latents"
        isLoading={isLoadingLatents}
        choices={allLatents?.map((latent) => ({
          value: latent.name,
          count: latent.image_count,
        })) || []}
        selected={latents}
        onChange={(selected) => setLatents(selected)}
        allowMultiple={true}
      />
      <ChoiceFilter
        label="Duplicate State"
        isLoading={false}
        choices={duplicateStateChoices}
        selected={duplicateState ? [duplicateState] : []}
        onChange={(selected) => setDuplicateState(selected[0])}
        allowMultiple={false}
      />
    </div>
  );
};
