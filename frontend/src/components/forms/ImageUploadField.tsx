import React, {useState, useEffect, useRef, ChangeEvent} from 'react';
import {CloudArrowUpIcon} from "@heroicons/react/24/outline";
import { twMerge } from 'tailwind-merge';

interface ImageUploadFieldProps {
  onUpload: (file: File) => void;
}

export const ImageUploadField: React.FC<ImageUploadFieldProps> = ({ onUpload }) => {
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent<Window>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragover") {
      setIsDragging(true);
    } else if (e.type === "dragleave" || e.type === "drop") {
      setIsDragging(false);
    }
  };

  const handleDrop = (e: React.DragEvent<Window>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onUpload(e.dataTransfer.files[0]);
    }
  };

  useEffect(() => {
    const dragOverListener = (e: DragEvent) => handleDrag(e as unknown as React.DragEvent<Window>);
    const dropListener = (e: DragEvent) => handleDrop(e as unknown as React.DragEvent<Window>);
    const dragLeaveListener = (e: DragEvent) => handleDrag(e as unknown as React.DragEvent<Window>);

    window.addEventListener("dragover", dragOverListener);
    window.addEventListener("drop", dropListener);
    window.addEventListener("dragleave", dragLeaveListener);

    return () => {
      window.removeEventListener("dragover", dragOverListener);
      window.removeEventListener("drop", dropListener);
      window.removeEventListener("dragleave", dragLeaveListener);
    };
  }, []);

  const handleOpenDialog = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      onUpload(event.target.files[0]);
    }
  };

  return (
    <div className={twMerge(
        "px-2 py-4 border border-dashed rounded-lg text-center text-sm cursor-pointer transition-colors",
        "border-black/30 hover:border-black/40 hover:bg-black/5",
        "dark:border-white/30 dark:hover:border-white/40 dark:hover:bg-white/5",
      )}
      onClick={handleOpenDialog}>
      {
        isDragging && <div className="flex items-center justify-center text-white text-lg fixed top-0 left-0 right-0 bottom-0 z-40 bg-black/80">
          <div className="flex flex-col items-center gap-4">
            <CloudArrowUpIcon className="w-16 h-16" />
            <p>Drop the image here to find similar images</p>
            <p><button onClick={() => {setIsDragging(false)}}>Cancel</button></p>
          </div>
        </div>
      }
      <p className="text-xs">Choose an image<br/>or drag and drop it anywhere</p>
      <input type="file" ref={fileInputRef} style={{display: 'none'}} onChange={handleFileChange} />
    </div>
  );
};
