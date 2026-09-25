export type DrawerMode = "closed" | "peek" | "open";

/** Follow the queue unless the drawer is covering the page. */
export function nextDrawer(mode: DrawerMode, follow: boolean, activeCount: number): DrawerMode {
  if (!follow || mode === "open") return mode;
  if (activeCount > 0) return "peek";
  if (mode === "peek") return "closed";
  return mode;
}

const HANDLE = 52;

/**
 * A short upward drag with a job in flight shows that job.
 * A long drag covers the page. A downward drag closes.
 */
export function snapDrawer(height: number, viewport: number, hasJob: boolean): DrawerMode {
  if (height > viewport * 0.55) return "open";
  if (height < HANDLE + 28) return "closed";
  if (hasJob) return "peek";
  if (height > viewport * 0.34) return "open";
  return "closed";
}
