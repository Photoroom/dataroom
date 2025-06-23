import React, { useEffect } from "react";
import { useImageListData } from "../../context/ImageListDataContext";
import { ImageListMode } from "../../context/ImageListDataContext";
import { ArrowsRightLeftIcon, MagnifyingGlassIcon } from "@heroicons/react/20/solid";
import { Image } from "../../components/image/Image";
import { TextField } from "../../components/forms/TextField";
import { OSImage } from "../../api/client.schemas";
import { ImageUploadField } from "../../components/forms/ImageUploadField";

enum SearchType {
  NONE = 'none',
  IMAGE = 'image',
  TEXT = 'text',
  FILE = 'file',
  VECTOR = 'vector',
}

interface GetSearchTypeProps {
  mode: ImageListMode;
  similarImage: OSImage | null;
  similarText: string | null;
  similarFile: File | null;
  similarVector: string | null;
}

const getSearchType = (props: GetSearchTypeProps) => {
  const { mode, similarImage, similarText, similarFile, similarVector } = props;
  if (mode === ImageListMode.SIMILAR && similarImage) {
    return SearchType.IMAGE;
  }
  if (mode === ImageListMode.SIMILAR && similarText) {
    return SearchType.TEXT;
  }
  if (mode === ImageListMode.SIMILAR && similarFile) {
    return SearchType.FILE;
  }
  if (mode === ImageListMode.SIMILAR && similarVector) {
    return SearchType.VECTOR;
  }
  return SearchType.NONE;
}

export const SearchForm: React.FC = () => {
  const {
    mode,
    similarImage,
    setModeSimilarImage,
    similarText,
    setModeSimilarText,
    similarFile,
    setModeSimilarFile,
    similarVector,
    setModeSimilarVector,
  } = useImageListData();

  const [textInput, setTextInput] = React.useState<string>(similarText || '');
  const [vectorInput, setVectorInput] = React.useState<string>(similarVector || '');

  const [searchType, setSearchType] = React.useState<SearchType>(getSearchType({
    mode,
    similarImage,
    similarText,
    similarFile,
    similarVector,
  }));
  
  useEffect(() => {
    setSearchType(getSearchType({
      mode,
      similarImage,
      similarText,
      similarFile,
      similarVector,
    }));
  }, [mode, similarImage, similarText, similarFile, similarVector]);

  // -------------------- Similar image --------------------
  if (searchType === SearchType.IMAGE && similarImage) {
    return (
      <div className="grid grid-cols-4 gap-2 bg-black/8 dark:bg-white/8 rounded-lg pr-2 pl-3 py-2">
        <div className="col-span-3 text-xs">
          <ArrowsRightLeftIcon className="inline-block mr-1 size-3 shrink-0" />
          Similar to:<br/><span className="font-bold break-all">{similarImage.id}</span>
        </div>
        <Image image={similarImage} />
      </div>
    );
  }

  // -------------------- Similar image --------------------
  if (searchType === SearchType.FILE) {
    if (similarFile) {
      return (
        <div className="grid grid-cols-4 gap-2 bg-black/8 dark:bg-white/8 rounded-lg pr-2 pl-3 py-2">
          <div className="col-span-3 text-xs">
            <ArrowsRightLeftIcon className="inline-block mr-1 size-3 shrink-0" />
            Similar to:<br/><span className="font-bold break-all">Uploaded file</span>
          </div>
          <div className="w-full aspect-square rounded-lg bg-black/8 dark:bg-white/8 bg-cover bg-center" style={{backgroundImage: `url('${URL.createObjectURL(similarFile)}')`}}></div>
        </div>
      );
    } else {
      return (
        <ImageUploadField onUpload={(file) => { setModeSimilarFile(file) }} />
      );
    }
  }

  // -------------------- Similar vector --------------------
  if (searchType === SearchType.VECTOR) {
    return (
      <div>
        <TextField
          name="vector"
          value={vectorInput}
          onChange={(e) => {
            setVectorInput(e.target.value);
          }}
          className="pr-8"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              setModeSimilarVector(vectorInput);
            }
          }}
          inputRight={
            <button type="button"
              className="pl-2 pr-3 cursor-pointer h-full opacity-50 hover:opacity-100 transition-opacity"
              onClick={() => {
                setModeSimilarVector(vectorInput);
              }}
            >
              <MagnifyingGlassIcon className="size-4" />
            </button>
          }
        />
      </div>
    );
  }
  
  // -------------------- Text search --------------------
  if (searchType === SearchType.TEXT) {
    return (
      <div>
        <TextField
          name="text"
          value={textInput}
          onChange={(e) => {
            setTextInput(e.target.value);
          }}
          className="pr-8"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              setModeSimilarText(textInput);
            }
          }}
          inputRight={
            <button type="button"
              className="pl-2 pr-3 cursor-pointer h-full opacity-50 hover:opacity-100 transition-opacity"
              onClick={() => {
                setModeSimilarText(textInput);
              }}
            >
              <MagnifyingGlassIcon className="size-4" />
            </button>
          }
        />
      </div>
    );
  }

  // -------------------- Select search type --------------------
  return (
    <div className="grid grid-cols-3 gap-2">
      <button className="btn btn-outline btn-sm" onClick={() => { setSearchType(SearchType.TEXT) }}>Text</button>
      <button className="btn btn-outline btn-sm" onClick={() => { setSearchType(SearchType.FILE) }}>Image</button>
      <button className="btn btn-outline btn-sm" onClick={() => { setSearchType(SearchType.VECTOR) }}>Vector</button>
    </div>
  );
};
