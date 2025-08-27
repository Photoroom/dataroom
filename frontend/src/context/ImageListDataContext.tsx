import React, { createContext, useContext, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  imagesRandomRetrieve,
  imagesRetrieve,
  useImagesList,
  useImagesRandomRetrieve,
  useImagesSimilarList,
  useImagesSimilarToFileCreate,
  useImagesSimilarToTextCreate,
  useImagesSimilarToVectorCreate,
} from "../api/client";
import { OSImage, PaginatedOSImage } from "../api/client.schemas";
import { axiosInstance } from "../api/axios";
import toast from "react-hot-toast";

export enum ImageListMode {
  BROWSE = "browse",
  RANDOM = "random",
  SIMILAR = "similar",
}

export interface ImageListFilters {
  sources: string[];
  tags: string[];
  aspect_ratio_fraction: string | null;
  has_attributes: string[];
  has_latents: string[];
  duplicate_state: string | null;
  datasets: string[];
}

interface ImageListDataContextType {
  // image list
  images: OSImage[];
  isLoadingImages: boolean;
  isLoadingImagesError: boolean;
  hasNextPage: boolean;
  loadNextPage: () => void;
  isLoadingNextPage: boolean;
  isLoadingNextPageError: boolean;
  // mode
  mode: ImageListMode;
  setModeBrowse: () => void;
  setModeRandom: () => void;
  // similarity search
  setModeSimilarImage: (imageId: string) => void;
  similarImage: OSImage | null;
  setModeSimilarText: (text: string) => void;
  similarText: string | null;
  setModeSimilarFile: (file: File) => void;
  similarFile: File | null;
  setModeSimilarVector: (vector: string) => void;
  similarVector: string | null;
  // selecting
  isSelecting: boolean;
  setIsSelecting: (isSelecting: boolean) => void;
  selectedImages: string[];
  toggleSelectedImage: (imageId: string, isMultiSelect: boolean) => void;
  clearSelectedImages: () => void;
  // random
  randomPrefixLength: number;
  setRandomPrefixLength: (prefixLength: number) => void;
  randomNumPrefixes: number;
  setRandomNumPrefixes: (numPrefixes: number) => void;
  // filters
  filters: ImageListFilters;
  setFilters: (filters: ImageListFilters) => void;
}

const ImageListDataContext = createContext<ImageListDataContextType | undefined>(undefined);

// -------------------- Constants --------------------
const LIST_INCLUDE_FIELDS = "thumbnail,image";
const PAGE_SIZE = 100;

// -------------------- Data provider --------------------
export function ImageListDataProvider({ children }: { children: React.ReactNode }) {
  const [searchParams, setSearchParams] = useSearchParams();

  // -------------------- Get initial URL state --------------------
  const initialRandomPrefixLength = searchParams.get("prefix_length") ? Number(searchParams.get("prefix_length")) : 5;
  const initialRandomNumPrefixes = searchParams.get("num_prefixes") ? Number(searchParams.get("num_prefixes")) : 100;
  const initialSimilarImageId = searchParams.get("similar") || null;
  const initialSimilarText = searchParams.get("similarText") || null;

  // -------------------- Mode state --------------------
  const [randomPrefixLength, setRandomPrefixLength] = useState(initialRandomPrefixLength);
  const [randomNumPrefixes, setRandomNumPrefixes] = useState(initialRandomNumPrefixes);

  const [mode, setMode] = useState<ImageListMode>(() => {
    if (searchParams.get("similar") || searchParams.get("similarText")) {
      return ImageListMode.SIMILAR;
    } else if (searchParams.get("random") == "true") {
      return ImageListMode.RANDOM;
    } else {
      return ImageListMode.BROWSE;
    }
  });

  const setModeBrowse = () => {
    setMode(ImageListMode.BROWSE);
    setSimilarImageId(null);
    setSimilarText(null);
    setSimilarFile(null);
    setSimilarVector(null);
  };

  const setModeRandom = () => {
    setMode(ImageListMode.RANDOM);
  };

  // -------------------- Similar image --------------------
  const [similarImageId, setSimilarImageId] = useState<string | null>(initialSimilarImageId);
  const [similarImage, setSimilarImage] = useState<OSImage | null>(null);

  const setModeSimilarImage = (imageId: string) => {
    setMode(ImageListMode.SIMILAR);
    setSimilarText(null);
    setSimilarFile(null);
    setSimilarVector(null);
    setSimilarImageId(imageId);
  };

  useEffect(() => {
    if (similarImageId) {
      imagesRetrieve(similarImageId, {
        include_fields: LIST_INCLUDE_FIELDS,
      })
        .then(response => {
          setSimilarImage(response);
        })
        .catch(e => {
          toast.error("Error loading similar image");
          console.error(e);
        });
    } else {
      setSimilarImage(null);
    }
  }, [similarImageId]);

  // -------------------- Similar text --------------------
  const [similarText, setSimilarText] = useState<string | null>(initialSimilarText);

  const setModeSimilarText = (text: string) => {
    setMode(ImageListMode.SIMILAR);
    setSimilarImageId(null);
    setSimilarImage(null);
    setSimilarFile(null);
    setSimilarVector(null);
    setSimilarText(text);
  };

  // -------------------- Similar file --------------------
  const [similarFile, setSimilarFile] = useState<File | null>(null);

  const setModeSimilarFile = (file: File) => {
    setMode(ImageListMode.SIMILAR);
    setSimilarImageId(null);
    setSimilarImage(null);
    setSimilarText(null);
    setSimilarVector(null);
    setSimilarFile(file);
  };

  // -------------------- Similar vector --------------------
  const [similarVector, setSimilarVector] = useState<string | null>(null);

  const setModeSimilarVector = (vector: string) => {
    setMode(ImageListMode.SIMILAR);
    setSimilarImageId(null);
    setSimilarImage(null);
    setSimilarText(null);
    setSimilarFile(null);
    setSimilarVector(vector);
  };

  // -------------------- Image list state --------------------
  const [images, setImages] = useState<OSImage[]>([]);
  const [imagesNextUrl, setImagesNextUrl] = useState<string | null>(null);
  const [isLoadingNextPage, setIsLoadingNextPage] = useState(false);
  const [isLoadingNextPageError, setIsLoadingNextPageError] = useState(false);

  // -------------------- Keep URL state in sync --------------------

  // update the URL when the mode changes
  useEffect(() => {
    const newParams = new URLSearchParams(searchParams);

    // random mode
    if (mode === ImageListMode.RANDOM) {
      setImagesNextUrl(null);
      newParams.set("random", "true");
      newParams.set("prefix_length", randomPrefixLength.toString());
      newParams.set("num_prefixes", randomNumPrefixes.toString());
    } else {
      setImagesNextUrl(null);
      newParams.delete("random");
      newParams.delete("prefix_length");
      newParams.delete("num_prefixes");
    }

    // similar mode
    if (mode === ImageListMode.SIMILAR && similarImageId) {
      setImagesNextUrl(null); // no pagination
      newParams.set("similar", similarImageId);
    } else {
      newParams.delete("similar");
    }
    if (mode === ImageListMode.SIMILAR && similarText) {
      setImagesNextUrl(null); // no pagination
      newParams.set("similarText", similarText);
    } else {
      newParams.delete("similarText");
    }
    if (mode === ImageListMode.SIMILAR && similarFile) {
      setImagesNextUrl(null); // no pagination
      newParams.set("similarFile", "true");
    } else {
      newParams.delete("similarFile");
    }
    if (mode === ImageListMode.SIMILAR && similarVector) {
      setImagesNextUrl(null); // no pagination
      newParams.set("similarVector", "true");
    } else {
      newParams.delete("similarVector");
    }

    // update the search params
    setSearchParams(newParams);
  }, [mode, randomPrefixLength, randomNumPrefixes, similarImageId, similarText, similarFile, similarVector]);

  // -------------------- Selecting images --------------------
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectedImages, setSelectedImages] = useState<string[]>([]);
  const [lastSelectedImage, setLastSelectedImage] = useState(null as string | null);
  const [lastWasUnselected, setLastWasUnselected] = useState(false);

  const toggleSelectedImage = (imageId: string, isMultiSelect: boolean) => {
    const isAlreadySelected = selectedImages.includes(imageId);

    if (isMultiSelect && lastSelectedImage) {
      const lastSelectedIndex = images.findIndex(image => image.id === lastSelectedImage);
      const currentSelectedIndex = images.findIndex(image => image.id === imageId);
      const start = Math.min(lastSelectedIndex, currentSelectedIndex);
      const end = Math.max(lastSelectedIndex, currentSelectedIndex);
      const selectedIds = images.slice(start, end + 1).map(image => image.id);
      if (lastWasUnselected) {
        setSelectedImages(selectedImages.filter(id => !selectedIds.includes(id)));
      } else {
        setSelectedImages(
          selectedImages.concat(selectedIds).filter((value, index, self) => self.indexOf(value) === index)
        );
      }
    } else {
      if (isAlreadySelected) {
        setSelectedImages(selectedImages.filter(id => id !== imageId));
      } else {
        setSelectedImages([...selectedImages, imageId]);
      }
    }
    setLastSelectedImage(imageId);
    setLastWasUnselected(isAlreadySelected);
  };

  const clearSelectedImages = () => {
    setSelectedImages([]);
  };

  // -------------------- Filters --------------------
  const [filters, setFilters] = useState<ImageListFilters>(() => {
    return {
      sources: searchParams.get("sources")?.split(",") || [],
      tags: searchParams.get("tags")?.split(",") || [],
      aspect_ratio_fraction: searchParams.get("aspect_ratio_fraction") || null,
      has_attributes: searchParams.get("has_attributes")?.split(",") || [],
      has_latents: searchParams.get("has_latents")?.split(",") || [],
      duplicate_state: searchParams.get("duplicate_state") || null,
      datasets: searchParams.get("datasets")?.split(",") || [],
    };
  });

  const getFiltersParams = (filters: ImageListFilters): { [key: string]: string } => {
    let params: { [key: string]: string } = {};
    for (const [key, value] of Object.entries(filters)) {
      if (value) {
        if (Array.isArray(value)) {
          if (value.length > 0) {
            params[key] = value.join(",");
          } else {
            // skip it
          }
        } else {
          params[key] = value;
        }
      }
    }
    return params;
  };

  // keep URL in sync with filters
  useEffect(() => {
    const newParams = new URLSearchParams(searchParams);
    newParams.delete("sources");
    newParams.delete("tags");
    newParams.delete("aspect_ratio_fraction");
    newParams.delete("has_attributes");
    newParams.delete("has_latents");
    newParams.delete("duplicate_state");
    newParams.delete("datasets");
    const filtersParams = getFiltersParams(filters);
    for (const [key, value] of Object.entries(filtersParams)) {
      newParams.set(key, value);
    }
    setSearchParams(newParams);
  }, [filters]);

  // -------------------- Fetching image list --------------------

  useEffect(() => {
    // Reset images when mode changes
    setImages([]);
    setImagesNextUrl(null);
  }, [mode, randomPrefixLength, randomNumPrefixes, similarImageId, similarText, similarFile, similarVector]);

  // Browse mode query
  const browseQuery = useImagesList(
    {
      ...getFiltersParams(filters),
      include_fields: LIST_INCLUDE_FIELDS,
      page_size: PAGE_SIZE,
    },
    {
      query: {
        enabled: mode === ImageListMode.BROWSE,
      },
    }
  );

  // Random mode query
  const randomQuery = useImagesRandomRetrieve(
    {
      ...getFiltersParams(filters),
      include_fields: LIST_INCLUDE_FIELDS,
      page_size: PAGE_SIZE,
      prefix_length: randomPrefixLength,
      num_prefixes: randomNumPrefixes,
    },
    {
      query: {
        enabled: mode === ImageListMode.RANDOM,
      },
    }
  );

  // Similar image query
  const similarImageQuery = useImagesSimilarList(
    similarImageId || "",
    {
      include_fields: LIST_INCLUDE_FIELDS,
      number: PAGE_SIZE,
    },
    {
      query: {
        enabled: mode === ImageListMode.SIMILAR && !!similarImageId,
      },
    }
  );

  // Similar text mutation
  const similarTextMutation = useImagesSimilarToTextCreate();

  useEffect(() => {
    if (mode === ImageListMode.SIMILAR && similarText) {
      similarTextMutation.mutate({
        data: {
          text: similarText,
          number: PAGE_SIZE,
        },
        params: {
          include_fields: LIST_INCLUDE_FIELDS,
        },
      });
    }
  }, [mode, similarText]);

  // Similar file mutation
  const similarFileMutation = useImagesSimilarToFileCreate();

  useEffect(() => {
    if (mode === ImageListMode.SIMILAR && similarFile) {
      similarFileMutation.mutate({
        data: {
          image: similarFile,
          json: JSON.stringify({ number: PAGE_SIZE }),
        },
        params: {
          include_fields: LIST_INCLUDE_FIELDS,
        },
      });
    }
  }, [mode, similarFile]);

  // Similar vector mutation
  const similarVectorMutation = useImagesSimilarToVectorCreate();

  useEffect(() => {
    if (mode === ImageListMode.SIMILAR && similarVector) {
      similarVectorMutation.mutate({
        data: {
          vector: similarVector,
          number: PAGE_SIZE,
        },
        params: {
          include_fields: LIST_INCLUDE_FIELDS,
        },
      });
    }
  }, [mode, similarVector]);

  // Set up data when queries complete
  useEffect(() => {
    if (mode === ImageListMode.BROWSE && browseQuery.data) {
      setImages(browseQuery.data.results);
      setImagesNextUrl(browseQuery.data.next);
    } else if (mode === ImageListMode.RANDOM && randomQuery.data) {
      setImages(randomQuery.data.results);
      setImagesNextUrl(randomQuery.data.next);
    } else if (mode === ImageListMode.SIMILAR && similarImageId && similarImageQuery.data) {
      setImages(similarImageQuery.data || []);
      setImagesNextUrl(null);
    } else if (mode === ImageListMode.SIMILAR && similarText && similarTextMutation.data) {
      setImages(similarTextMutation.data || []);
      setImagesNextUrl(null);
    } else if (mode === ImageListMode.SIMILAR && similarFile && similarFileMutation.data) {
      setImages(similarFileMutation.data || []);
      setImagesNextUrl(null);
    } else if (mode === ImageListMode.SIMILAR && similarVector && similarVectorMutation.data) {
      setImages(similarVectorMutation.data || []);
      setImagesNextUrl(null);
    }
  }, [
    browseQuery.data,
    randomQuery.data,
    similarImageQuery.data,
    similarTextMutation.data,
    similarFileMutation.data,
    similarVectorMutation.data,
    mode,
    similarImageId,
    similarText,
    similarFile,
    similarVector,
  ]);

  // Handle errors
  useEffect(() => {
    if (browseQuery.error && mode === ImageListMode.BROWSE) {
      toast.error("Error loading images");
      console.error(browseQuery.error);
    }
    if (randomQuery.error && mode === ImageListMode.RANDOM) {
      toast.error("Error loading random images");
      console.error(randomQuery.error);
    }
    if (similarImageQuery.error && mode === ImageListMode.SIMILAR && similarImageId) {
      toast.error("Error loading similar images");
      console.error(similarImageQuery.error);
    }
    if (similarTextMutation.error && mode === ImageListMode.SIMILAR && similarText) {
      toast.error("Error loading similar to text");
      console.error(similarTextMutation.error);
    }
    if (similarFileMutation.error && mode === ImageListMode.SIMILAR && similarFile) {
      toast.error("Error loading similar to file");
      console.error(similarFileMutation.error);
    }
    if (similarVectorMutation.error && mode === ImageListMode.SIMILAR && similarVector) {
      toast.error("Error loading similar to vector");
      console.error(similarVectorMutation.error);
    }
  }, [
    browseQuery.error,
    randomQuery.error,
    similarImageQuery.error,
    similarTextMutation.error,
    similarFileMutation.error,
    similarVectorMutation.error,
    mode,
    similarImageId,
    similarText,
    similarFile,
    similarVector,
  ]);

  // Combine loading states
  const isLoadingImages = !!(
    (mode === ImageListMode.BROWSE && browseQuery.isLoading) ||
    (mode === ImageListMode.RANDOM && randomQuery.isLoading) ||
    (mode === ImageListMode.SIMILAR && similarImageId && similarImageQuery.isLoading) ||
    (mode === ImageListMode.SIMILAR && similarText && similarTextMutation.isPending) ||
    (mode === ImageListMode.SIMILAR && similarFile && similarFileMutation.isPending) ||
    (mode === ImageListMode.SIMILAR && similarVector && similarVectorMutation.isPending)
  );

  // Combine error states
  const isLoadingImagesError = !!(
    (mode === ImageListMode.BROWSE && browseQuery.isError) ||
    (mode === ImageListMode.RANDOM && randomQuery.isError) ||
    (mode === ImageListMode.SIMILAR && similarImageId && similarImageQuery.isError) ||
    (mode === ImageListMode.SIMILAR && similarText && similarTextMutation.isError) ||
    (mode === ImageListMode.SIMILAR && similarFile && similarFileMutation.isError) ||
    (mode === ImageListMode.SIMILAR && similarVector && similarVectorMutation.isError)
  );

  // next page function
  const loadNextPage = async () => {
    if (mode === ImageListMode.BROWSE) {
      // ------------ Browse mode ------------
      // use the next page value
      if (!imagesNextUrl) {
        return;
      }
      setIsLoadingNextPage(true);
      setIsLoadingNextPageError(false);
      axiosInstance<PaginatedOSImage>({
        method: "GET",
        url: imagesNextUrl,
      })
        .then(response => {
          const { results } = response;
          setImages([...images, ...results]);
          setImagesNextUrl(response.next);
        })
        .catch(e => {
          toast.error("Error loading next page of images");
          console.error(e);
          setIsLoadingNextPageError(true);
        })
        .finally(() => {
          setIsLoadingNextPage(false);
        });
    } else if (mode === ImageListMode.RANDOM) {
      // ------------ Random mode ------------
      // hit the same endpoint again
      setIsLoadingNextPage(true);
      setIsLoadingNextPageError(false);
      imagesRandomRetrieve({
        include_fields: LIST_INCLUDE_FIELDS,
        page_size: PAGE_SIZE,
        prefix_length: randomPrefixLength,
        num_prefixes: randomNumPrefixes,
      })
        .then(response => {
          const { results } = response;
          setImages([...images, ...results]);
          setImagesNextUrl(response.next);
        })
        .catch(e => {
          toast.error("Error loading next page of random images");
          console.error(e);
          setIsLoadingNextPageError(true);
        })
        .finally(() => {
          setIsLoadingNextPage(false);
        });
    } else if (mode === ImageListMode.SIMILAR) {
      // ------------ Similar mode ------------
      // pagination for similar images is not supported
    }
  };

  // -------------------- Return --------------------
  return (
    <ImageListDataContext.Provider
      value={{
        // image list
        images,
        isLoadingImages,
        isLoadingImagesError,
        hasNextPage: imagesNextUrl !== null,
        loadNextPage,
        isLoadingNextPage,
        isLoadingNextPageError,
        // mode
        mode,
        setModeBrowse,
        setModeRandom,
        // similarity search
        setModeSimilarImage,
        similarImage,
        setModeSimilarText,
        similarText,
        setModeSimilarFile,
        similarFile,
        setModeSimilarVector,
        similarVector,
        // selecting
        isSelecting,
        setIsSelecting,
        selectedImages,
        toggleSelectedImage,
        clearSelectedImages,
        // random
        randomPrefixLength,
        setRandomPrefixLength,
        randomNumPrefixes,
        setRandomNumPrefixes,
        // filters
        filters,
        setFilters,
      }}
    >
      {children}
    </ImageListDataContext.Provider>
  );
}

// hook to use the image data context
export function useImageListData() {
  const context = useContext(ImageListDataContext);
  if (context === undefined) {
    throw new Error("useImageListData must be used within a ImageListDataContext");
  }
  return context;
}
