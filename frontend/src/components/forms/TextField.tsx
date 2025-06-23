import React, { InputHTMLAttributes, forwardRef } from 'react';
import { twMerge } from 'tailwind-merge';
import { Label } from './Label';

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: string;
  label?: string;
  helpText?: string;
  formWidgetClass?: string;
  inputRight?: React.ReactNode;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(({
  error,
  label,
  helpText,
  className,
  formWidgetClass,
  disabled,
  onChange,
  inputRight,
  ...props
}, ref) => {
  const inputClasses = twMerge(
    'block w-full border',
    'disabled:cursor-not-allowed disabled:opacity-50',
    'bg-white border-black/20 text-black placeholder-black/20',
    'outline-none focus:ring-1 focus:border-primary-500 focus:ring-primary-500',
    'dark:border-white/10 dark:bg-black/20 dark:text-white dark:placeholder-white/20',
    'p-1.5 px-2.5 text-sm rounded-lg',
    formWidgetClass,
    className,
    error && 'border-rose-500 dark:border-rose-500',
  );

  const id = props.name ? `id_${props.name}` : undefined;

  return (
    <div className="flex flex-col gap-1">
      {label && <Label htmlFor={id} label={label} helpText={helpText} />}
      <div className="relative">
        <input
          type="text"
          disabled={disabled}
          className={inputClasses}
          ref={ref}
          onChange={onChange}
          id={id}
          {...props}
        />
        {inputRight && <div className="absolute inset-y-0 right-0 flex items-center">{inputRight}</div>}
      </div>
      {error && (
        <span className="text-sm text-rose-500 dark:text-rose-400">{error}</span>
      )}
    </div>
  );
});

TextField.displayName = 'TextField';
