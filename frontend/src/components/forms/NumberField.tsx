import React, { forwardRef } from 'react';
import { TextField } from './TextField';

interface NumberFieldProps extends Omit<React.ComponentProps<typeof TextField>, 'type'> {}

export const NumberField = forwardRef<HTMLInputElement, NumberFieldProps>((props, ref) => {
  const preventWheelChange = (e: React.WheelEvent<HTMLInputElement>) => {
    // Prevent the input from changing value on scroll
    e.currentTarget.blur();
  };

  return (
    <TextField
      type="number"
      onWheel={preventWheelChange}
      ref={ref}
      {...props}
    />
  );
});

NumberField.displayName = 'NumberField';
