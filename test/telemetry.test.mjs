import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateTelemetry, summarizeTelemetry } from '../telemetry.mjs';

test('spatial data accepts screen coordinates and rejects content or invalid estimates', () => {
  assert.deepEqual(validateTelemetry({ gaze_x: 0, gaze_y: 1, cursor_x: 1920, cursor_y: 100, screen_width: 1920, screen_height: 1080, action: 'left_click' }).gaze_y, 1);
  for (const details of [{ gaze_x: 1.1 }, { gaze_y: NaN }, { screenshot: 'data' }, { typedText: 'private' }, { action: 'execute' }, { screen_width: 0 }]) assert.throws(() => validateTelemetry(details));
});
test('heatmap uses normalized gaze boundaries and counts interaction types separately', () => {
  const summary = summarizeTelemetry([{ kind: 'gaze', time: 10, details: { gaze_x: 0, gaze_y: 0 } }, { kind: 'gaze', time: 11, details: { gaze_x: 1, gaze_y: 1 } }, { kind: 'click' }, { kind: 'key' }, { kind: 'tracking_lost' }]);
  assert.equal(summary.heatmap[0], 1); assert.equal(summary.heatmap[59], 1);
  assert.equal(summary.gazeSamples, 2); assert.equal(summary.clicks, 1); assert.equal(summary.keys, 1); assert.equal(summary.trackingLosses, 1);
});
