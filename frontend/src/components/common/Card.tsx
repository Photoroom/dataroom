import React from 'react';
import { twMerge } from 'tailwind-merge';

interface CardProps {
  className?: string;
  children: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({ className = '', children }) => {
  return (
    <div className={twMerge("flex flex-col gap-2 w-full rounded-lg bg-white dark:bg-white/8", className)}>
      {children}
    </div>
  );
};
