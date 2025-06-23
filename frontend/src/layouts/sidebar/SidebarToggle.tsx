import React from "react";
import { ToggleButton } from "../../components/forms/ToggleButton";


interface SidebarToggleProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
  checked: boolean;
  children?: React.ReactNode;
}


export const SidebarToggle: React.FC<SidebarToggleProps> = function ({ icon: Icon, label, onClick, checked, children }) {
  
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-row items-center justify-between">
        <div className="flex flex-row gap-2 flex-1 cursor-pointer" onClick={onClick}>
          <Icon className="size-5" />
          <span className="text-sm">{label}</span>
        </div>
        <ToggleButton onChange={onClick} checked={checked} />
      </div>
      {Boolean(checked) === true && children}
    </div>
  );
};
