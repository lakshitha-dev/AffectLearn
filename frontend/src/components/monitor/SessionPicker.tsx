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
  activeIds,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  sessionIds: string[];
  /**
   * Session ids with a live WebSocket right now.
   *
   * `/monitor/sessions` returns `active[]` alongside the recent-buffer ids, but only the latter
   * were used — so a session that ended ten minutes ago looked exactly like one in progress.
   */
  activeIds?: Set<string>;
}) {
  return (
    <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? null : v)}>
      <SelectTrigger className="w-56">
        <SelectValue placeholder="All sessions" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>All sessions</SelectItem>
        {sessionIds.map((sid) => {
          const live = activeIds?.has(sid) ?? false;
          return (
            <SelectItem key={sid} value={sid}>
              <span className="flex items-center gap-2">
                <span
                  aria-hidden
                  className={
                    "h-1.5 w-1.5 shrink-0 rounded-full " +
                    (live ? "bg-green-500" : "bg-muted-foreground/40")
                  }
                />
                {shortId(sid)}
                <span className="text-[10px] text-muted-foreground">
                  {live ? "live" : "ended"}
                </span>
              </span>
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}
