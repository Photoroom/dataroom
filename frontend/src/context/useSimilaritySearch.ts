import { useEffect, useState } from "react";
import {
  imagesRetrieve,
  useImagesSimilarList,
  useImagesSimilarToFileCreate,
  useImagesSimilarToTextCreate,
  useImagesSimilarToVectorCreate,
} from "../api/client";
import { OSImage } from "../api/client.schemas";
import toast from "react-hot-toast";
import { ImageListMode } from "./ImageListDataContext";

const LIST_INCLUDE_FIELDS = "thumbnail,image";
const PAGE_SIZE = 100;

interface UseSimilaritySearchInput {
  mode: ImageListMode;
  setMode: (mode: ImageListMode) => void;
  onImagesLoaded: (images: OSImage[], nextUrl: string | null) => void;
  initialSimilarImageId: string | null;
  initialSimilarText: string | null;
}

export function useSimilaritySearch({
  mode,
  setMode,
  onImagesLoaded,
  initialSimilarImageId,
  initialSimilarText,
}: UseSimilaritySearchInput) {
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

  // -------------------- Set browse (clears all similarity) --------------------
  const setModeBrowse = () => {
    setMode(ImageListMode.BROWSE);
    setSimilarImageId(null);
    setSimilarText(null);
    setSimilarFile(null);
    setSimilarVector(null);
  };

  // -------------------- Queries & Mutations --------------------

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

  // -------------------- Set up data when queries complete --------------------
  useEffect(() => {
    if (mode === ImageListMode.SIMILAR && similarImageId && similarImageQuery.data) {
      onImagesLoaded(similarImageQuery.data || [], null);
    } else if (mode === ImageListMode.SIMILAR && similarText && similarTextMutation.data) {
      onImagesLoaded(similarTextMutation.data || [], null);
    } else if (mode === ImageListMode.SIMILAR && similarFile && similarFileMutation.data) {
      onImagesLoaded(similarFileMutation.data || [], null);
    } else if (mode === ImageListMode.SIMILAR && similarVector && similarVectorMutation.data) {
      onImagesLoaded(similarVectorMutation.data || [], null);
    }
  }, [
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

  // -------------------- Handle errors --------------------
  useEffect(() => {
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

  // -------------------- Compose loading/error --------------------
  const isLoading = !!(
    (mode === ImageListMode.SIMILAR && similarImageId && similarImageQuery.isLoading) ||
    (mode === ImageListMode.SIMILAR && similarText && similarTextMutation.isPending) ||
    (mode === ImageListMode.SIMILAR && similarFile && similarFileMutation.isPending) ||
    (mode === ImageListMode.SIMILAR && similarVector && similarVectorMutation.isPending)
  );

  const isError = !!(
    (mode === ImageListMode.SIMILAR && similarImageId && similarImageQuery.isError) ||
    (mode === ImageListMode.SIMILAR && similarText && similarTextMutation.isError) ||
    (mode === ImageListMode.SIMILAR && similarFile && similarFileMutation.isError) ||
    (mode === ImageListMode.SIMILAR && similarVector && similarVectorMutation.isError)
  );

  return {
    similarImageId,
    similarImage,
    setModeSimilarImage,
    similarText,
    setModeSimilarText,
    similarFile,
    setModeSimilarFile,
    similarVector,
    setModeSimilarVector,
    setModeBrowse,
    isLoading,
    isError,
  };
}
