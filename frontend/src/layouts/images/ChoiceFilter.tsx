import React, { useState } from "react";
import { Checkbox } from "../../components/forms/Checkbox";
import { Radio } from "../../components/forms/Radio";
import { XMarkIcon } from "@heroicons/react/20/solid";
import { twMerge } from "tailwind-merge";
import { LoaderSkeleton } from "../../components/common/LoaderSkeleton";
import { shortNumberDisplay } from "../../utils/shortNumberDisplay";

type Choice = {
  value: string;
  label?: string;
  count?: number;
};

interface ChoiceItemProps {
  choice: Choice;
  checked: boolean;
  onChange: (checked: boolean) => void;
  allowMultiple: boolean;
}

const ChoiceItem: React.FC<ChoiceItemProps> = ({ choice, checked, onChange, allowMultiple }) => {
  const Comp = allowMultiple ? Checkbox : Radio;
  return (
    <Comp
      label={<>{choice.label ? choice.label : choice.value} {choice.count !== undefined && <span className="opacity-50">({shortNumberDisplay(choice.count)})</span>}</>}
      checked={checked}
      onChange={onChange}
    />
  );
};

interface ChoiceFilterProps {
  label: string,
  isLoading: boolean,
  choices: Choice[];
  selected: string[];
  onChange: (selected: string[]) => void;
  allowMultiple?: boolean;
  initialShowCount?: number;
}

export const ChoiceFilter: React.FC<ChoiceFilterProps> = ({
  label,
  isLoading,
  choices,
  selected,
  onChange,
  allowMultiple = false,
  initialShowCount = 5,
}) => {
  const [showAll, setShowAll] = useState(false);
  const hasMoreChoices = choices.length > initialShowCount;
  const initialChoices = choices.slice(0, initialShowCount);
  const remainingChoices = choices.slice(initialShowCount);
  
  const hiddenCount = choices.length - initialShowCount;

  const handleChoiceChange = (choice: Choice, checked: boolean) => {
    if (allowMultiple) {
      onChange(checked ? [...selected, choice.value] : selected.filter((s) => s !== choice.value));
    } else {
      onChange([choice.value]);
    }
  };

  return (
    <div className="flex flex-col gap-2 pb-4 border-b border-black/10 dark:border-white/10">
      <div className="flex flex-row gap-2 items-center justify-between">
        <p className="text-sm">{label}</p>
        {selected.length > 0 && (
          <button className="text-xs flex flex-row items-center opacity-50 cursor-pointer hover:opacity-100" onClick={() => onChange([])}>
            <XMarkIcon className="size-4" /> Clear
          </button>
        )}
      </div>
      <div className="flex flex-col gap-2 px-0.5">
        {
          isLoading && (<>
            <LoaderSkeleton />
            <LoaderSkeleton />
            <LoaderSkeleton />
          </>
          )
        }

        {initialChoices.map((choice) => (
          <ChoiceItem
            key={choice.value}
            choice={choice}
            checked={selected.includes(choice.value)}
            onChange={(checked) => handleChoiceChange(choice, checked)}
            allowMultiple={allowMultiple}
          />
        ))}
        
        {hasMoreChoices && (
          <div className="flex flex-col gap-2">
            <div 
              className={twMerge(
                "grid transition-all ease-in-out",
                showAll ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
              )}
            >
              <div className="overflow-hidden">
                <div className="flex flex-col gap-2">
                  {remainingChoices.map((choice) => (
                    <ChoiceItem
                      key={choice.value}
                      choice={choice}
                      checked={selected.includes(choice.value)}
                      onChange={(checked) => handleChoiceChange(choice, checked)}
                      allowMultiple={allowMultiple}
                    />
                  ))}
                </div>
              </div>
            </div>
            
            <button 
              className="self-start text-xs cursor-pointer opacity-50 hover:opacity-100"
              onClick={() => setShowAll(!showAll)}
            >
              {showAll ? "Show less" : `Show ${hiddenCount} more`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

