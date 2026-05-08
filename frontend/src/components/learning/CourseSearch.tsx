"use client";

import { Search, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";

interface CourseSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function CourseSearch({
  value,
  onChange,
  placeholder = "Search courses",
  className,
}: CourseSearchProps) {
  return (
    <div className={cn("relative w-full", className)}>
      <Search
        aria-hidden
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
      />
      <Input
        type="search"
        role="searchbox"
        aria-label="Search courses"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 pl-9 pr-9"
      />
      {value.length > 0 ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-border focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}
