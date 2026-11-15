import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDocumentVisible, usePolling } from "./useApi";

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
});

describe("visibility-aware polling", () => {
  it("reflects document visibility changes", () => {
    const { result } = renderHook(() => useDocumentVisible());
    expect(result.current).toBe(true);

    act(() => setHidden(true));
    expect(result.current).toBe(false);

    act(() => setHidden(false));
    expect(result.current).toBe(true);
  });

  it("pauses polling while hidden and resumes when visible", async () => {
    const loader = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => usePolling(loader, 40));

    await waitFor(() => expect(result.current.data).toBe("ok"));
    const callsBeforeHide = loader.mock.calls.length;

    act(() => setHidden(true));
    await new Promise((resolve) => setTimeout(resolve, 140));
    expect(loader.mock.calls.length).toBe(callsBeforeHide);

    act(() => setHidden(false));
    await waitFor(() => expect(loader.mock.calls.length).toBeGreaterThan(callsBeforeHide));

    // Let the resumed request settle before the test environment is torn down.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 80));
    });
  });
});
