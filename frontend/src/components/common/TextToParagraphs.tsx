import React from "react";
import { twMerge } from "tailwind-merge";

interface TextToParagraphsProps {
  text?: string | null;
  className?: string;
}

export const TextToParagraphs = ({ text, className }: TextToParagraphsProps) => {
  if (!text) return null;

  const paragraphs = text.split("\n");

  return (
    <div className={twMerge("flex flex-col gap-1", className)}>
      {paragraphs.map((paragraph, index) => paragraph.trim() !== "" && <p key={index}>{paragraph}</p>)}
    </div>
  );
};
