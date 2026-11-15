import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Job } from "../api/types";
import { api } from "../api/client";
import { useJob } from "./useApi";

vi.mock("../api/client", () => ({
  api: {
    job: vi.fn(),
    events: vi.fn(),
  },
}));

const jobMock = vi.mocked(api.job);
const eventsMock = vi.mocked(api.events);

let hidden = false;

function setHidden(value: boolean) {
  hidden = value;
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => hidden,
  });
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => (hidden ? "hidden" : "visible"),
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

beforeEach(() => {
  setHidden(false);
  jobMock.mockReset();
  eventsMock.mockReset();
  jobMock.mockResolvedValue({ id: "job-1", status: "running" } as Job);
  eventsMock.mockResolvedValue({ events: [] });
});

describe("useJob visibility", () => {
  it("stops polling hidden tabs and resumes when visible", async () => {
    const { result } = renderHook(() => useJob("job-1"));

    await waitFor(() => expect(result.current.job?.status).toBe("running"));
    const callsBeforeHide = jobMock.mock.calls.length;

    act(() => setHidden(true));
    await new Promise((resolve) => setTimeout(resolve, 1400));
    expect(jobMock.mock.calls.length).toBe(callsBeforeHide);

    act(() => setHidden(false));
    await waitFor(() => expect(jobMock.mock.calls.length).toBeGreaterThan(callsBeforeHide));
  });
});
