import React, { useEffect, useState } from "react";
import { twMerge } from "tailwind-merge";
import { OSImage } from "../../api/client.schemas";
import { ImagePopup } from "./ImagePopup";
import ReactDOM from "react-dom";

interface ImagePreviewProps {
  image?: OSImage;
  width: number;
  className?: string;
}

export const ImagePreview: React.FC<ImagePreviewProps> = ({ 
  image, 
  width, 
  className 
}) => {

  // -------------------- Popup --------------------
  const [isPopupOpen, setIsPopupOpen] = useState(false);

  const handleClosePopup = () => {
    setIsPopupOpen(false);
  };

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    setIsPopupOpen(true);
  };

  // -------------------- Keyboard Events --------------------
  useEffect(() => {
    const handleEscKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isPopupOpen) {
        handleClosePopup();
      }
    };

    window.addEventListener('keydown', handleEscKey);
    
    return () => {
      window.removeEventListener('keydown', handleEscKey);
    };
  }, [isPopupOpen]);


  // -------------------- Dimensions --------------------
  const defaultHeight = 200;
  const [imgHeight, setImgHeight] = useState(defaultHeight);
  
  useEffect(() => {
    if (image?.aspect_ratio) {
      setImgHeight(width / image.aspect_ratio);
    } else {
      setImgHeight(defaultHeight);
    }
  }, [image, width]);


  // -------------------- Render --------------------
  return (
    <>
      <a href={image?.image} onClick={handleClick} className={twMerge(
        "flex items-center justify-center mx-auto md:mx-0 bg-black/8 dark:bg-white/8",
        image ? "" : "animate-pulse rounded-sm",
        className
      )}
      style={{
        minHeight: imgHeight,
        maxWidth: width,
        backgroundSize: 'contain',
        backgroundImage: `url('${image?.thumbnail}')` // use thumbnail for faster previews
      }}>
        {image && <img src={image.image} alt="" className="min-w-full h-auto"/>}
      </a>
      {
        image && (
          ReactDOM.createPortal(
            <ImagePopup image={image} isOpen={isPopupOpen} onClose={handleClosePopup} />,
            document.body
          )
        )
      }
    </>
  );
};
