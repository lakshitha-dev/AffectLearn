"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { shortId } from "./shared";

const ALL = "__all__";

export function SessionPicker({
  value,
  onChange,
  sessionIds,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  sessionIds: string[];
}) {
  return (
    <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? null : v)}>
      <SelectTrigger className="w-56">
        <SelectValue placeholder="All sessions" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>All sessions</SelectItem>
        {sessionIds.map((sid) => (
          <SelectItem key={sid} value={sid}>
            {shortId(sid)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
