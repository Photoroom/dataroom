import React, { forwardRef } from "react";
import { TextField } from "./TextField";

export const NumberField = forwardRef<HTMLInputElement, Omit<React.ComponentProps<typeof TextField>, "type">>(
  (props, ref) => {
    const preventWheelChange = (e: React.WheelEvent<HTMLInputElement>) => {
      // Prevent the input from changing value on scroll
      e.currentTarget.blur();
    };

    return <TextField type="number" onWheel={preventWheelChange} ref={ref} {...props} />;
  }
);

NumberField.displayName = "NumberField";
