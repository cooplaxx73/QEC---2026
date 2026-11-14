// Only spatial/interaction metadata is accepted. No screen or typed content.
export function validateTelemetry(input) {
  if (input === undefined) return {};
  if (!input || Array.isArray(input) || typeof input !== 'object') throw new Error('Invalid activity details.');
  const rules = { gaze_x: [0, 1], gaze_y: [0, 1], cursor_x: [-32768, 65536], cursor_y: [-32768, 65536], screen_width: [1, 32768], screen_height: [1, 32768], screen_left: [-32768, 32768], screen_top: [-32768, 32768] };
  const result = {};
  for (const [key, value] of Object.entries(input)) {
    if (key === 'action') {
      if (!['left_click', 'right_click', 'double_click', 'zoom_left_click'].includes(value)) throw new Error('Invalid click action.');
    } else {
      if (!Object.hasOwn(rules, key) || typeof value !== 'number' || !Number.isFinite(value) || value < rules[key][0] || value > rules[key][1]) throw new Error('Invalid activity detail: ' + key);
    }
    result[key] = value;
  }
  return result;
}

export function summarizeTelemetry(logs) {
  const heatmap = Array(60).fill(0);
  const summary = { total: logs.length, gazeSamples: 0, clicks: 0, keys: 0, trackingLosses: 0, heatmap, latestGaze: null, retainedLimit: 20000 };
  for (const e of logs) {
    if (e.kind === 'click') summary.clicks++;
    if (e.kind === 'key') summary.keys++;
    if (e.kind === 'tracking_lost') summary.trackingLosses++;
    if (e.kind === 'gaze' && typeof e.details?.gaze_x === 'number' && typeof e.details?.gaze_y === 'number') {
      summary.gazeSamples++;
      heatmap[Math.min(5, Math.floor(e.details.gaze_y * 6)) * 10 + Math.min(9, Math.floor(e.details.gaze_x * 10))]++;
      summary.latestGaze = { time: e.time, ...e.details };
    }
  }
  return summary;
}
