import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { useSegments } from "./useApi";

vi.mock("../api/client", () => ({
  api: {
    segments: vi.fn(),
  },
}));

const segmentsMock = vi.mocked(api.segments);

beforeEach(() => {
  segmentsMock.mockReset();
});

describe("useSegments", () => {
  it("loads segments and duration", async () => {
    segmentsMock.mockResolvedValue({
      segments: [{
        idx: 0, job_id: "job-1", start: 0, end: 1,
        text_src: "Hello", text_es: "Hola", status: "ready",
      }],
      duration: 3,
    });

    const { result } = renderHook(() => useSegments("job-1"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.segments).toHaveLength(1);
    expect(result.current.duration).toBe(3);
  });

  it("exposes load errors instead of rejecting silently", async () => {
    segmentsMock.mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useSegments("job-1"));

    await waitFor(() => expect(result.current.error?.message).toBe("boom"));
    expect(result.current.loading).toBe(false);
    expect(result.current.segments).toEqual([]);
  });
});
