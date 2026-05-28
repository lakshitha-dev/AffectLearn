interface LessonProgressBarProps {
  value: number;
}

export function LessonProgressBar({ value }: LessonProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div
      className="h-1 w-full bg-border"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Lesson progress"
    >
      <div
        className="h-full bg-primary transition-[width] duration-150 ease-linear"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
