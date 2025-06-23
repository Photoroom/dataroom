import React from 'react';
import { twMerge } from 'tailwind-merge';
import { LabelTooltip } from './LabelTooltip';

interface LabelProps {
  htmlFor?: string;
  label: string;
  helpText?: string;
  className?: string;
}

export const Label: React.FC<LabelProps> = ({ htmlFor, label, helpText, className }) => {
  return (
    <label htmlFor={htmlFor} className={twMerge("flex flex-row items-center gap-1 text-xs text-gray-900 dark:text-gray-300", className)}>
      <span>{label}</span>
      {helpText && <LabelTooltip content={helpText} />}
    </label>
  );
};
